"""PhaseOrchestrator — executes pipeline phases and returns ArtifactPointer lists.

This module is the dispatcher: it maintains the phase-to-handler strategy map,
wraps handler execution in structured result contracts, and exposes shared
helpers used by the handler sub-modules.  The concrete phase logic lives in
``packages.pipeline_services.phases``.
"""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.domain_core.models import ArtifactPointer, ExecutionFailure
from packages.domain_core.phase_execution import (
    PhaseExecutionFailure,
    PhaseExecutionResult,
    PhaseExecutionSuccess,
)
from packages.pipeline_services.force_align_service import ForceAlignError
from packages.pipeline_services.phases import (
    classify_tts_error,
    load_montage_inputs,
    run_asset,
    run_final_rendering,
    run_final_review,
    run_montage_assembly,
    run_scene_assembly,
    run_script,
    run_subtitle,
    run_tts,
    run_tts_review,
    run_video_rendering,
    _build_tts_provider as _build_tts_provider_fn,
    _discover_script as _discover_script_fn,
    _discover_sentence_timings as _discover_sentence_timings_fn,
    _get_ffmpeg_path as _get_ffmpeg_path_fn,
    _get_media_duration as _get_media_duration_fn,
    _job_dir as _job_dir_fn,
    _resolve_api_key as _resolve_api_key_fn,
    _resolve_api_url as _resolve_api_url_fn,
    _resolve_categories as _resolve_categories_fn,
    _resolve_llm_config as _resolve_llm_config_fn,
    _resolve_scene_folders as _resolve_scene_folders_fn,
    _resolve_tts_config as _resolve_tts_config_fn,
    _scene_candidates as _scene_candidates_fn,
    _to_artifact as _to_artifact_fn,
    to_url_path,
)
from packages.pipeline_services.sentence_tts_service import SentenceTiming
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore

STRUCTURED_MEDIA_PHASES = frozenset(
    {
        "tts_generating",
        "scene_assembling",
        "subtitle_generating",
        "montage_assembling",
        "video_rendering",
        "final_rendering",
    }
)

__all__ = [
    "STRUCTURED_MEDIA_PHASES",
    "PhaseContext",
    "PhaseOrchestrator",
    "create_orchestrator",
    "to_url_path",
]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def create_orchestrator(
    root_dir: Path, config_reader: ConfigReader
) -> "PhaseOrchestrator":
    """Factory: build a PhaseOrchestrator with real service dependencies.

    *config_reader* is required — all config reads go through it.
    """
    from packages.pipeline_services.subtitle_service import SubtitleService
    from packages.pipeline_services.video_service import VideoService

    return PhaseOrchestrator(
        subtitle_svc=SubtitleService(),
        video_svc=VideoService(dry_run=False),
        config_reader=config_reader,
    )


# ---------------------------------------------------------------------------
# PhaseContext
# ---------------------------------------------------------------------------


@dataclass
class PhaseContext:
    """Carries all per-invocation context that a phase handler needs."""

    job_id: str
    project_dir: Path
    root_dir: Path
    product: str
    brand: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    # Import-mode scene fields
    scene_folder_paths: list[str] = field(default_factory=list)
    transition_duration_ms: int = 500
    # Full scene config dict (populated by caller from ConfigReader);
    # when non-empty, handlers use this instead of reading config themselves.
    scene_config: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PhaseOrchestrator
# ---------------------------------------------------------------------------


class PhaseOrchestrator:
    """Strategy-map dispatcher: one handler per phase, injected dependencies."""

    def __init__(
        self,
        subtitle_svc: Any,
        video_svc: Any,
        *,
        schedule_store: Any = None,
        config_reader: ConfigReader | None = None,
        secret_store: SecretStore | None = None,
        get_tts_config: Callable[[], dict[str, Any]] | None = None,
        get_llm_config: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._subtitle_svc = subtitle_svc
        self._video_svc = video_svc
        self._schedule_store = schedule_store
        self._config = config_reader
        self._secrets = secret_store if secret_store is not None else SecretStore()
        self._get_tts_config = get_tts_config
        self._get_llm_config = get_llm_config

        self._handlers: dict[str, Callable[[PhaseContext], list[ArtifactPointer]]] = {
            "script_generating": lambda ctx: run_script(self, ctx),
            "tts_generating": lambda ctx: run_tts(self, ctx),
            "tts_review": lambda ctx: run_tts_review(self, ctx),
            "subtitle_generating": lambda ctx: run_subtitle(self, ctx),
            "asset_retrieving": lambda ctx: run_asset(self, ctx),
            "video_rendering": lambda ctx: run_video_rendering(self, ctx),
            "final_rendering": lambda ctx: run_final_rendering(self, ctx),
            "final_review": lambda ctx: run_final_review(self, ctx),
            "scene_assembling": lambda ctx: run_scene_assembly(self, ctx),
            "montage_assembling": lambda ctx: run_montage_assembly(self, ctx),
        }

    # -- public interface ---------------------------------------------------

    def run_phase(self, phase: str, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute *phase* and return the artifacts it produced.

        Raises ``ValueError`` if *phase* is unknown.
        """
        handler = self._handlers.get(phase)
        if handler is None:
            raise ValueError(
                f"Unknown phase: {phase!r}.  Known: {list(self._handlers)}"
            )
        return handler(ctx)

    def execute_phase(self, phase: str, ctx: PhaseContext) -> PhaseExecutionResult:
        """Execute a phase handler and return a structured result."""

        if phase not in STRUCTURED_MEDIA_PHASES:
            return PhaseExecutionSuccess(artifacts=self.run_phase(phase, ctx))

        validation_error = self.validate_phase_input(phase, ctx)
        if validation_error is not None:
            return PhaseExecutionFailure(error=validation_error)

        try:
            artifacts = self.run_phase(phase, ctx)
        except (TimeoutError, subprocess.TimeoutExpired):
            return PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="MEDIA_PROCESSING_TIMEOUT",
                    message=f"{phase} media processing timed out.",
                    retryable=True,
                )
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            return PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="MEDIA_INPUT_INVALID",
                    message=f"{phase} input is invalid: {exc}",
                    retryable=False,
                )
            )
        except ForceAlignError as exc:
            # Uploaded audio alignment failure — non-retryable data-quality issue
            detail = "\n".join(d.summary() for d in exc.result.diagnostics)
            return PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="UPLOAD_AUDIO_ALIGN_FAILED",
                    message=(
                        f"Uploaded audio force-alignment failed: {exc.result.message}"
                        f"\n{detail}"
                    ),
                    retryable=False,
                )
            )
        except Exception as exc:
            # Provider-specific TTS error classification (#253)
            if phase == "tts_generating":
                return self._classify_tts_error(phase, exc)
            return PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="MEDIA_PROCESSING_FAILED",
                    message=f"{phase} media processing failed: {exc}",
                    retryable=True,
                )
            )

        if not artifacts:
            return PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="INTERNAL_EMPTY_RESULT",
                    message=f"{phase} reported success without an artifact.",
                    retryable=False,
                )
            )
        return PhaseExecutionSuccess(artifacts=artifacts)

    def _classify_tts_error(self, phase: str, exc: Exception) -> PhaseExecutionFailure:
        """Classify a TTS provider error into a structured failure (#253)."""
        return classify_tts_error(phase, exc)

    def validate_phase_input(
        self, phase: str, ctx: PhaseContext
    ) -> ExecutionFailure | None:
        """Validate a media phase using the same contract as execution/retry."""

        job_dir = self._job_dir(ctx)
        if phase == "tts_generating":
            if not self._discover_script(job_dir):
                return ExecutionFailure(
                    code="TTS_SCRIPT_MISSING",
                    message="Script text is required before TTS audio can be synthesized.",
                    retryable=False,
                )
            # Check for uploaded audio: validate source file exists
            uploaded_audio_path: str = ctx.options.get("uploaded_audio_path", "")
            if uploaded_audio_path:
                src_audio = ctx.root_dir / uploaded_audio_path
                if not src_audio.exists():
                    return ExecutionFailure(
                        code="UPLOAD_AUDIO_NOT_FOUND",
                        message=f"Uploaded audio file not found: {uploaded_audio_path}",
                        retryable=False,
                    )
        if phase == "scene_assembling":
            # Snapshot exists → local copies available, skip source-folder check
            if (job_dir / ".scene_snapshot" / "manifest.json").exists():
                return None
            folders = self._resolve_scene_folders(ctx)
            if not folders:
                return ExecutionFailure(
                    code="SCENE_INPUT_MISSING",
                    message="No scene folders are configured for this Job.",
                    retryable=False,
                )
            missing_folders = [folder for folder in folders if not folder.exists()]
            if missing_folders:
                return ExecutionFailure(
                    code="SCENE_FOLDER_NOT_FOUND",
                    message=f"Scene folder does not exist: {missing_folders[0].as_posix()}",
                    retryable=False,
                )
            if not any(self._scene_candidates(folder) for folder in folders):
                return ExecutionFailure(
                    code="SCENE_MEDIA_MISSING",
                    message="Configured scene folders contain no usable video files.",
                    retryable=False,
                )
        elif phase == "subtitle_generating":
            if not (job_dir / "audio.mp3").exists():
                return ExecutionFailure(
                    code="SUBTITLE_AUDIO_MISSING",
                    message="audio.mp3 is required before subtitles can be generated.",
                    retryable=False,
                )
            if not self._discover_script(job_dir):
                return ExecutionFailure(
                    code="SUBTITLE_SCRIPT_MISSING",
                    message="Script text is required before subtitles can be generated.",
                    retryable=False,
                )
        elif phase == "montage_assembling":
            _, _, error = self._load_montage_inputs(ctx)
            return error
        elif phase == "video_rendering":
            if not (job_dir / "montage_segment.mp4").exists():
                return ExecutionFailure(
                    code="VIDEO_MONTAGE_SEGMENT_MISSING",
                    message="The montage segment is required before video rendering.",
                    retryable=False,
                )
            return None
        elif phase == "final_rendering":
            missing = [
                name
                for name in ("base.mp4", "audio.mp3")
                if not (job_dir / name).exists()
            ]
            skip_subtitle = False
            job_json = ctx.project_dir / "control" / "jobs" / f"{ctx.job_id}.json"
            if job_json.exists():
                try:
                    skip_subtitle = bool(
                        json.loads(job_json.read_text(encoding="utf-8")).get(
                            "skip_subtitle", False
                        )
                    )
                except json.JSONDecodeError:
                    return ExecutionFailure(
                        code="MEDIA_INPUT_INVALID",
                        message="The Job settings file is invalid.",
                        retryable=False,
                    )
            if not skip_subtitle and not (job_dir / "subtitles.srt").exists():
                missing.append("subtitles.srt")
            if missing:
                return ExecutionFailure(
                    code="FINAL_RENDER_INPUT_MISSING",
                    message=f"Final rendering requires: {', '.join(missing)}.",
                    retryable=False,
                )
        return None

    def execute_phases_parallel(
        self, phases: list[str], ctx: PhaseContext
    ) -> dict[str, PhaseExecutionResult]:
        """Run structured phase boundaries concurrently without hiding failures."""

        results: dict[str, PhaseExecutionResult] = {}
        with ThreadPoolExecutor(max_workers=len(phases)) as executor:
            future_map = {
                executor.submit(self.execute_phase, phase, ctx): phase
                for phase in phases
            }
            for future in as_completed(future_map):
                phase_name = future_map[future]
                try:
                    result: PhaseExecutionResult = future.result()
                except Exception as exc:
                    if phase_name in STRUCTURED_MEDIA_PHASES:
                        raise
                    print(f"[PARALLEL] Phase {phase_name} failed: {exc}", flush=True)
                    result = PhaseExecutionFailure(
                        error=ExecutionFailure(
                            code="MEDIA_PROCESSING_FAILED",
                            message=f"{phase_name} media processing failed: {exc}",
                            retryable=True,
                        )
                    )
                # A legacy handler that produced nothing must not surface as
                # an empty success — the structured contract has no such
                # sentinel.  (Structured phases already convert this case in
                # execute_phase.)
                if isinstance(result, PhaseExecutionSuccess) and not result.artifacts:
                    result = PhaseExecutionFailure(
                        error=ExecutionFailure(
                            code="INTERNAL_EMPTY_RESULT",
                            message=(
                                f"{phase_name} reported success without an artifact."
                            ),
                            retryable=False,
                        )
                    )
                results[phase_name] = result
        return results

    # -- helpers ------------------------------------------------------------

    def _job_dir(self, ctx: PhaseContext) -> Path:
        """Return (and ensure) the job's runtime output directory."""
        return _job_dir_fn(ctx)

    def _to_artifact(self, kind: str, path: Path, workspace_dir: Path) -> ArtifactPointer:
        """Build an ``ArtifactPointer`` from an absolute file path."""
        return _to_artifact_fn(kind, path, workspace_dir)

    # -- config resolution helpers (ConfigReader-first, fallback to callbacks) --

    def _resolve_tts_config(self, ctx: PhaseContext) -> dict[str, Any]:
        """Resolve TTS config via ConfigReader."""
        return _resolve_tts_config_fn(self, ctx)

    def _resolve_llm_config(self, ctx: PhaseContext) -> dict[str, Any]:
        """Resolve LLM config via ConfigReader."""
        return _resolve_llm_config_fn(self, ctx)

    def _resolve_api_key(self, llm_config: dict[str, Any]) -> str:
        """Resolve API key via SecretStore."""
        return _resolve_api_key_fn(self, llm_config)

    def _resolve_api_url(self, llm_config: dict[str, Any]) -> str:
        """Resolve API base URL via SecretStore."""
        return _resolve_api_url_fn(self, llm_config)

    def _resolve_categories(self, ctx: PhaseContext) -> list[str]:
        """Resolve category names for asset classification."""
        return _resolve_categories_fn(self, ctx)

    def _build_tts_provider(self, tts_cfg: dict[str, Any]) -> Any:
        """Build TTS provider dynamically from current config."""
        return _build_tts_provider_fn(self, tts_cfg)

    # -- discovery helpers --------------------------------------------------

    def _discover_script(self, job_dir: Path) -> str | None:
        """Return the script text from *口播文案.txt or *口播文案.json, or None."""
        return _discover_script_fn(job_dir)

    def _discover_sentence_timings(self, job_dir: Path) -> list[SentenceTiming]:
        """Return sentence timings from sentences.json if present and valid."""
        return _discover_sentence_timings_fn(job_dir)

    def _resolve_scene_folders(self, ctx: PhaseContext) -> list[Path]:
        """Resolve scene folder paths from context, config or ConfigReader."""
        return _resolve_scene_folders_fn(ctx, self._config)

    def _scene_candidates(self, folder: Path) -> list[Path]:
        """Return usable video files inside a scene folder."""
        return _scene_candidates_fn(folder)

    def _load_montage_inputs(
        self, ctx: PhaseContext
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], ExecutionFailure | None]:
        """Load and validate the immutable inputs for ``montage_assembling``."""
        return load_montage_inputs(ctx)

    # -- ffmpeg helpers (lazy imports) -----------------------------------------

    def _get_ffmpeg_path(self) -> str:
        """Resolve ffmpeg path via media_utils."""
        return _get_ffmpeg_path_fn()

    def _get_media_duration(self, file_path: Path) -> float:
        """Get media duration in seconds via ffprobe."""
        return _get_media_duration_fn(file_path)

    def _create_sentence_tts_service(
        self, provider: Any, tts_cfg: dict[str, Any], ctx: PhaseContext
    ) -> Any:
        """Factory hook for the sentence-level TTS service (overridable in tests)."""
        from packages.pipeline_services.phases.tts import _create_sentence_tts_service

        return _create_sentence_tts_service(provider, tts_cfg, ctx)

    # -- legacy handler entry points (kept for backward-compatible callers) ----

    def _run_script(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute script generation (legacy method, delegates to handler)."""
        return run_script(self, ctx)

    def _run_tts(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute TTS synthesis (legacy method, delegates to handler)."""
        return run_tts(self, ctx)

    def _run_tts_review(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute TTS review (legacy method, delegates to handler)."""
        return run_tts_review(self, ctx)

    def _run_subtitle(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute subtitle generation (legacy method, delegates to handler)."""
        return run_subtitle(self, ctx)

    def _run_asset(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute asset retrieval (legacy method, delegates to handler)."""
        return run_asset(self, ctx)

    def _run_video(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute video rendering (legacy method, delegates to handler)."""
        return run_video_rendering(self, ctx)

    def _run_final_rendering(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute final rendering (legacy method, delegates to handler)."""
        return run_final_rendering(self, ctx)

    def _run_final(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute final review gate (legacy method, delegates to handler)."""
        return run_final_review(self, ctx)

    def _run_scene_assembly(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute scene assembly (legacy method, delegates to handler)."""
        return run_scene_assembly(self, ctx)

    def _run_montage_assembly(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute montage assembly (legacy method, delegates to handler)."""
        return run_montage_assembly(self, ctx)
