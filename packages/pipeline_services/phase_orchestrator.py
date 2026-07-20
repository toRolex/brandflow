"""PhaseOrchestrator — executes pipeline phases and returns ArtifactPointer lists.

This module extracts the logic from ``app._phase_to_artifacts`` (285-line god function)
into small, testable, injectable handler methods.

Slice 1: ``script_generating`` only.  Subsequent slices migrate remaining phases.
Slice 2: ``tts_generating``.
Slice 4: ConfigReader injection — all config reads use ConfigReader (no AppConfigManager).
"""

from __future__ import annotations

import json
import shutil
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
from packages.pipeline_services.script_service import generate_script
from packages.pipeline_services.script_service.generator import ScriptGenerator
from packages.pipeline_services.force_align_service import (
    ForceAlignError,
    ForceAlignService,
)
from packages.pipeline_services.final_timeline import (
    align_audio,
    build_final_timeline,
    compute_scene_offset_ms,
    shift_srt,
)
from packages.pipeline_services.script_sentence import parse_script_sentences
from packages.pipeline_services.sentence_tts_service import (
    SentenceTiming,
    SentenceTTSService,
)
from packages.pipeline_services.subtitle_service import SubtitleService
from packages.pipeline_services.video_service import VideoService
from packages.provider_config.config_reader import ConfigReader, ConfigResolver
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


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def to_url_path(path: Path, workspace_dir: Path) -> str:
    """Convert a workspace-relative *Path* to a URL-safe forward-slash string."""
    return path.relative_to(workspace_dir).as_posix()


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
# TTS config shim (duck-type, preserves tts_provider.synthesize() API)
# ---------------------------------------------------------------------------


class _TTSConfigShim:
    """Duck-type config object built from the TTS config dict.

    Preserves the interface expected by ``tts_provider.synthesize()``.
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.model: str = cfg.get("model", "mimo-v2.5-tts")
        self.voice: str = cfg.get("voice", "Mia")
        self.instructions: str = cfg.get("instructions", "")
        self.language_type: str = cfg.get("language_type", "")
        self.optimize_instructions: bool = cfg.get("optimize_instructions", False)
        self.fallback_voice: str = cfg.get("fallback_voice", "Dean")
        self.randomize_voice: bool = cfg.get("randomize_voice", False)
        self.random_voices: list[str] = cfg.get("random_voices", ["Mia", "Dean"])
        self.style_control_mode: str = cfg.get("style_control_mode", "simple")
        self.style_prompt: str = cfg.get("style_prompt", "自然 清晰")
        self.voice_design_prompt: str = cfg.get("voice_design_prompt", "")
        self.audio_format: str = cfg.get("audio_format", "wav")
        self.audio_tags_enabled: bool = cfg.get("audio_tags_enabled", False)
        self.audio_tags: str = cfg.get("audio_tags", "")
        self.voice_clone_sample_path: str = cfg.get("voice_clone_sample_path", "")
        self.voice_clone_mime_type: str = cfg.get("voice_clone_mime_type", "")
        self.optimize_text_preview: bool = cfg.get("optimize_text_preview", False)
        self.director_character: str = cfg.get("director_character", "")
        self.director_scene: str = cfg.get("director_scene", "")
        self.director_guidance: str = cfg.get("director_guidance", "")


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
        subtitle_svc: SubtitleService,
        video_svc: VideoService,
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
            "script_generating": self._run_script,
            "tts_generating": self._run_tts,
            "tts_review": self._run_tts_review,
            "subtitle_generating": self._run_subtitle,
            "asset_retrieving": self._run_asset,
            "video_rendering": self._run_video,
            "final_rendering": self._run_final_rendering,
            "final_review": self._run_final,
            "scene_assembling": self._run_scene_assembly,
            "montage_assembling": self._run_montage_assembly,
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

    @staticmethod
    def _classify_tts_error(phase: str, exc: Exception) -> PhaseExecutionFailure:
        """Classify a TTS provider error into a structured failure (#253).

        Provider-specific error types are mapped to vendor-agnostic error codes
        so the frontend and retry policy never depend on provider internals.
        """
        from packages.pipeline_services.tts_provider import (
            TTSBlockedError,
            TTSQuotaExceededError,
            TTSRetryableError,
        )

        if isinstance(exc, TTSQuotaExceededError):
            return PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="TTS_QUOTA_EXCEEDED",
                    message=f"TTS 配额超限，请稍后重试或更换模型: {exc}",
                    retryable=True,
                )
            )
        if isinstance(exc, TTSBlockedError):
            return PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="TTS_PROVIDER_REJECTED",
                    message=f"TTS 服务拒绝请求（鉴权失败或参数无效）: {exc}",
                    retryable=False,
                )
            )
        if isinstance(exc, TTSRetryableError):
            return PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="TTS_SYNTHESIS_FAILED",
                    message=f"TTS 合成失败（可重试）: {exc}",
                    retryable=True,
                )
            )
        # Unknown / network errors are retryable
        return PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_SYNTHESIS_FAILED",
                message=f"TTS 合成失败: {exc}",
                retryable=True,
            )
        )

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
        d = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _to_artifact(kind: str, path: Path, workspace_dir: Path) -> ArtifactPointer:
        """Build an ``ArtifactPointer`` from an absolute file path."""
        rel = to_url_path(path, workspace_dir)
        return ArtifactPointer(
            kind=kind,
            relative_path=rel,
            url=f"/workspace/{rel}",
            size_bytes=path.stat().st_size if path.exists() else 0,
        )

    # -- config resolution helpers (ConfigReader-first, fallback to callbacks) --

    def _resolve_tts_config(self, ctx: PhaseContext) -> dict[str, Any]:
        """Resolve TTS config via ConfigReader."""
        if self._config is not None:
            return self._config.get_tts_config(product_id=ctx.product)
        if self._get_tts_config is not None:
            return self._get_tts_config()
        raise RuntimeError(
            "No ConfigReader or TTS config callback available; "
            "create_orchestrator() requires a ConfigReader"
        )

    def _resolve_llm_config(self, ctx: PhaseContext) -> dict[str, Any]:
        """Resolve LLM config via ConfigReader."""
        if self._config is not None:
            return self._config.get_llm_config(product_id=ctx.product)
        if self._get_llm_config is not None:
            return self._get_llm_config()
        raise RuntimeError(
            "No ConfigReader or LLM config callback available; "
            "create_orchestrator() requires a ConfigReader"
        )

    def _resolve_api_key(self, llm_config: dict[str, Any]) -> str:
        """Resolve API key via SecretStore (replaces _resolve_llm_api_key + _resolve_asset_api_key)."""
        provider = llm_config.get("provider", "deepseek")
        return self._secrets.get_api_key(provider)

    def _resolve_api_url(self, llm_config: dict[str, Any]) -> str:
        """Resolve API base URL via SecretStore (replaces _resolve_llm_endpoint + _resolve_asset_api_url)."""
        provider = llm_config.get("provider", "deepseek")
        return self._secrets.get_api_base_url(provider)

    @staticmethod
    def _resolve_categories(
        config_reader: ConfigReader | None, ctx: PhaseContext
    ) -> list[str]:
        """Resolve category names for asset classification.

        Priority: product-level categories > asset_library categories > defaults.
        Uses ConfigReader when available; otherwise returns default food categories.
        """
        if config_reader is not None:
            product_config = config_reader.get_product_config(product_id=ctx.product)
            product_cats: list[dict] = product_config.get("categories", [])
            if product_cats:
                return [c.get("name", "") for c in product_cats if c.get("name")]

            al_config = config_reader.get_asset_library_config()
            raw: list[dict] = al_config.get("categories", [])
            if raw:
                return [c.get("name", "") for c in raw if c.get("name")]

        # Default food category names
        from packages.pipeline_services.asset_library.category_config import (
            default_categories,
        )

        return [c.name for c in default_categories()]

    def _build_tts_provider(self, tts_cfg: dict[str, Any]) -> Any:
        """Build TTS provider dynamically from current config.

        Reads model from *tts_cfg* and returns the matching provider instance
        so that config changes (e.g. mimo to qwen) take effect immediately
        without restarting the worker.

        API keys are resolved via SecretStore (replaces inline os.getenv closures).
        """
        from packages.pipeline_services.tts_provider import (
            MiMoTTSProvider,
            QwenTTSProvider,
        )

        tts_model = tts_cfg.get("model", "mimo-v2.5-tts") or ""

        if tts_model.startswith("qwen"):
            return QwenTTSProvider(
                api_key=self._secrets.get_api_key("qwen"),
                base_url=self._secrets.get_api_base_url("qwen")
                or "https://dashscope.aliyuncs.com/api/v1",
            )
        return MiMoTTSProvider(
            api_key=self._secrets.get_api_key("mimo"),
            base_url=self._secrets.get_api_base_url("mimo")
            or "https://api.xiaomimimo.com/v1",
        )

    # -- script_generating handler ------------------------------------------

    def _run_script(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute script generation (manual or LLM) and optional cover title."""
        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)
        manual_script: str = ctx.options.get("manual_script", "")
        result: list[ArtifactPointer] = []

        # 1. Generate or write script
        if manual_script:
            language = ctx.options.get("language", "mandarin")
            if language == "cantonese":
                try:
                    llm_cfg = self._resolve_llm_config(ctx)

                    class _LLMConfig:
                        api_key = self._resolve_api_key(llm_cfg)
                        base_url = self._resolve_api_url(llm_cfg)
                        model = llm_cfg.get("model", "deepseek-v4-pro")

                    gen = ScriptGenerator(_LLMConfig())
                    manual_script = gen.to_cantonese(
                        manual_script, ctx.product, ctx.brand
                    )
                    print("[SCRIPT] Converted manual script to Cantonese", flush=True)
                except Exception as e:
                    print(
                        f"[SCRIPT WARN] Cantonese conversion failed, using original: {e}",
                        flush=True,
                    )

            txt_path = job_dir / "口播文案.txt"
            txt_path.write_text(manual_script, encoding="utf-8")
            json_path = job_dir / "口播文案.json"
            json_path.write_text(
                json.dumps(
                    {"text": manual_script, "source": "manual"},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            script_result: dict[str, Any] = {
                "txt_path": str(txt_path),
                "json_path": str(json_path),
                "final_script": manual_script,
            }
        else:
            language = ctx.options.get("language", "mandarin")
            config_resolver = ConfigResolver(
                reader=self._config if self._config is not None else ConfigReader(),
                secrets=self._secrets,
            )
            script_result = generate_script(
                product=ctx.product,
                output_dir=job_dir,
                language=language,
                brand=ctx.brand,
                config_resolver=config_resolver,
            )

        # 2. Emit artifact pointers for txt + json
        txt_path = Path(script_result["txt_path"])
        json_path = Path(script_result["json_path"])
        for p in [txt_path, json_path]:
            if p.exists():
                result.append(self._to_artifact("script", p, workspace_dir))

        # 3. Auto-generate cover title (if not already set)
        self._maybe_generate_cover_title(ctx, script_result)

        return result

    def _maybe_generate_cover_title(
        self,
        ctx: PhaseContext,
        script_result: dict[str, Any],
    ) -> None:
        """Auto-generate cover title if the job JSON has no ``cover_title.text``.

        Uses ConfigReader for LLM config resolution.
        Errors are logged but never propagated.
        """
        job_json_path = ctx.project_dir / "control" / "jobs" / f"{ctx.job_id}.json"
        if not job_json_path.exists():
            return

        job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
        existing_ct = job_data.get("cover_title", {})
        if existing_ct and existing_ct.get("text"):
            return  # already set

        try:
            script_text = script_result.get("final_script", "")
            txt_path = Path(script_result.get("txt_path", ""))
            if not script_text and txt_path.exists():
                script_text = txt_path.read_text(encoding="utf-8").strip()
            if not script_text:
                return

            llm_config = self._resolve_llm_config(ctx)

            class _CoverConfig:
                api_key = self._resolve_api_key(llm_config)
                base_url = self._resolve_api_url(llm_config)
                model = llm_config.get("model", "deepseek-v4-pro")

            gen = ScriptGenerator(_CoverConfig())
            cover_title = gen.generate_cover_title(script_text, ctx.product, ctx.brand)
            job_data["cover_title"] = cover_title
            job_json_path.write_text(
                json.dumps(job_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"[COVER_TITLE] Auto-generated: {cover_title['text']}", flush=True)
        except Exception as e:
            print(f"[COVER_TITLE WARN] Failed to auto-generate: {e}", flush=True)

    # -- tts_generating handler ---------------------------------------------

    def _run_tts(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute per-sentence TTS synthesis or copy uploaded audio.

        Discovery order for uploaded audio:
            1. ``ctx.options["uploaded_audio_path"]`` → copy file, force-align,
               persist sentence timings, or raise ``ForceAlignError`` with
               per-sentence diagnostics.
            2. Otherwise discover script text from ``*口播文案.txt`` then ``*.json``
               and synthesize each canonical Script Sentence separately.
        """
        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)
        audio_path = job_dir / "audio.mp3"
        result: list[ArtifactPointer] = []
        uploaded_audio_path: str = ctx.options.get("uploaded_audio_path", "")

        if uploaded_audio_path:
            src_audio = ctx.root_dir / uploaded_audio_path
            if src_audio.exists():
                shutil.copy2(src_audio, audio_path)
                print(f"[TTS] Using uploaded audio: {src_audio}", flush=True)

                # Force-align uploaded audio to canonical Script Sentences
                existing_script = self._discover_script(job_dir)
                if existing_script:
                    sentences = parse_script_sentences(existing_script)
                    if sentences:
                        align_svc = ForceAlignService()
                        align_result = align_svc.align(audio_path, sentences)

                        if align_result.status == "success":
                            sentences_path = job_dir / "sentences.json"
                            sentences_path.write_text(
                                json.dumps(
                                    [t.model_dump() for t in align_result.timings],
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                                encoding="utf-8",
                            )
                            result.append(
                                self._to_artifact(
                                    "sentence_timings",
                                    sentences_path,
                                    workspace_dir,
                                )
                            )
                            print(
                                f"[TTS] Force-aligned uploaded audio: "
                                f"{len(align_result.timings)} sentences, "
                                f"audio size={audio_path.stat().st_size}",
                                flush=True,
                            )
                        else:
                            # No fallback — surface per-sentence diagnostics
                            raise ForceAlignError(align_result)
                    else:
                        print(
                            "[TTS] Uploaded audio: no parseable sentences in script",
                            flush=True,
                        )
                else:
                    print(
                        f"[TTS] Uploaded audio: no script text found in {job_dir}",
                        flush=True,
                    )
            else:
                print(f"[TTS WARN] Uploaded audio not found: {src_audio}", flush=True)
        else:
            existing_script = self._discover_script(job_dir)
            print(
                f"[TTS DEBUG] phase=tts_generating, script_found={existing_script is not None}, "
                f"len={len(existing_script) if existing_script else 0}",
                flush=True,
            )
            if existing_script:
                tts_cfg = self._resolve_tts_config(ctx)

                # Apply job-level TTS overrides (tts_model / tts_voice)
                # Priority: job override > provider defaults > global/product config
                job_tts_model: str = ctx.options.get("tts_model", "")
                job_tts_voice: str = ctx.options.get("tts_voice", "")
                if job_tts_model:
                    tts_cfg["model"] = job_tts_model
                if job_tts_voice:
                    tts_cfg["voice"] = job_tts_voice

                tts_provider = self._build_tts_provider(tts_cfg)
                service = self._create_sentence_tts_service(tts_provider, tts_cfg, ctx)
                # Per-sentence retry is handled inside SentenceTTSService
                # (ADR 0005).  When all sentence-level retries are exhausted
                # the provider error propagates to execute_phase, which
                # classifies it as a structured PhaseExecutionFailure (#253).
                timings = service.synthesize_script(existing_script, audio_path)

                sentences_path = job_dir / "sentences.json"
                sentences_path.write_text(
                    json.dumps(
                        [t.model_dump() for t in timings],
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                result.append(
                    self._to_artifact("sentence_timings", sentences_path, workspace_dir)
                )
                print(
                    f"[TTS] Synthesized: {audio_path.exists()}, "
                    f"size={audio_path.stat().st_size if audio_path.exists() else 0}",
                    flush=True,
                )
            else:
                print(f"[TTS WARN] No script text found in {job_dir}", flush=True)

        if audio_path.exists():
            result.append(self._to_artifact("tts_audio", audio_path, workspace_dir))

        return result

    def _create_sentence_tts_service(
        self, provider: Any, tts_cfg: dict[str, Any], ctx: PhaseContext
    ) -> SentenceTTSService:
        """Factory hook for the sentence-level TTS service (overridable in tests)."""
        cache_dir = ctx.root_dir / "workspace" / ".cache" / "tts"
        return SentenceTTSService(
            provider=provider,
            config=tts_cfg,
            cache_dir=cache_dir,
        )

    def _run_tts_review(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """tts_review: return existing audio artifact for review."""
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"
        audio_path = job_dir / "audio.mp3"
        if audio_path.exists():
            print(f"[TTS_REVIEW] Audio ready for review: {audio_path}", flush=True)
            return [self._to_artifact("tts_audio", audio_path, workspace_dir)]
        print(f"[TTS_REVIEW WARN] No audio found in {job_dir}", flush=True)
        return []

    def _run_subtitle(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """subtitle_generating: build SRT from audio + script text.

        When ``sentences.json`` is present, subtitle chunks are constrained to
        the Script Sentence boundaries so that no subtitle block crosses a
        sentence boundary.
        """
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        print(
            f"[SUBTITLE] audio exists={audio_path.exists()}, srt exists={srt_path.exists()}",
            flush=True,
        )
        if audio_path.exists():
            script_text = self._discover_script(job_dir) or ""
            print(
                f"[SUBTITLE] script found={bool(script_text)}, len={len(script_text)}",
                flush=True,
            )
            if script_text:
                try:
                    sentence_timings = self._discover_sentence_timings(job_dir)
                    if sentence_timings:
                        self._subtitle_svc.build_srt(
                            audio_path,
                            srt_path,
                            script_text,
                            sentence_timings=sentence_timings,
                        )
                    else:
                        self._subtitle_svc.build_srt(audio_path, srt_path, script_text)
                    print(f"[SUBTITLE] srt generated={srt_path.exists()}", flush=True)
                except Exception as e:
                    print(f"[SUBTITLE ERROR] {type(e).__name__}: {e}", flush=True)
                    import traceback

                    traceback.print_exc()
        else:
            print(f"[SUBTITLE WARN] audio.mp3 not found in {job_dir}", flush=True)
        if srt_path.exists():
            return [self._to_artifact("subtitle", srt_path, workspace_dir)]
        return []

    # -- asset_retrieving handler --------------------------------------------

    def _run_asset(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute semantic retrieval: script text -> keyword match -> selected clips."""
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"

        script_text = self._discover_script(job_dir)

        if not script_text:
            print("[ASSET] No script text found — emitting sentinel", flush=True)
            return [
                ArtifactPointer(
                    kind="asset_retrieval_done",
                    relative_path="",
                    url="",
                    size_bytes=0,
                )
            ]

        from packages.pipeline_services.asset_library import (
            AssetRepository,
            AssetRetriever,
        )
        from packages.pipeline_services.asset_library.classify import create_classify_fn

        db_path = ctx.root_dir / "workspace" / "shared_assets" / "asset_index.db"

        llm_config = self._resolve_llm_config(ctx)

        api_key = self._resolve_api_key(llm_config)
        api_url = self._resolve_api_url(llm_config)

        classify_fn = None
        if api_key and api_url:
            if not api_url.endswith("/chat/completions"):
                api_url = f"{api_url}/chat/completions"

            category_names = self._resolve_categories(self._config, ctx)

            classify_fn = create_classify_fn(
                api_url=api_url,
                api_key=api_key,
                model=self._config.get_category_suggestion_model()
                if self._config is not None
                else _fallback_category_suggestion_model(),
                category_names=category_names,
            )

        repo = AssetRepository(db_path)
        retriever = AssetRetriever(repo, classify_fn=classify_fn)

        selected = retriever.retrieve(script_text, ctx.product)

        clip_list_path = job_dir / "selected_clips.json"
        clip_list_path.write_text(
            json.dumps(selected, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(
            f"[ASSET] Retrieved {len(selected)} clips -> {clip_list_path}", flush=True
        )
        return [self._to_artifact("selected_clips", clip_list_path, workspace_dir)]

    # -- video_rendering handler ---------------------------------------------

    def _run_video(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """video_rendering: compose the base video from the Montage Segment.

        In import mode, the optional ``scene_segment.mp4`` is concatenated before
        the ``montage_segment.mp4``.  In generate mode (no scene), the montage
        segment is used directly as ``base.mp4``.

        The authoritative ``montage_segments.json`` produced by
        ``montage_assembling`` drives the Final Timeline so the montage layout is
        immutable and review-time decisions are preserved exactly.
        """
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"
        base_path = job_dir / "base.mp4"
        montage_path = job_dir / "montage_segment.mp4"
        scene_path = job_dir / "scene_segment.mp4"

        if not montage_path.exists():
            print(f"[VIDEO] No montage segment for {ctx.job_id}", flush=True)
            return []

        scene_exists = scene_path.exists()

        if scene_exists:
            # Concat scene segment + montage segment, normalizing both inputs.
            ffmpeg = self._get_ffmpeg_path()
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(scene_path),
                    "-i",
                    str(montage_path),
                    "-filter_complex",
                    "[0:v]settb=AVTB,fps=30,scale=720:1280:force_original_aspect_ratio=decrease,"
                    "pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,format=pix_fmts=yuv420p[v0];"
                    "[1:v]settb=AVTB,fps=30,scale=720:1280:force_original_aspect_ratio=decrease,"
                    "pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,format=pix_fmts=yuv420p[v1];"
                    "[v0][v1]concat=n=2:v=1:a=0[v]",
                    "-map",
                    "[v]",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(base_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=600,
            )
            print(f"[VIDEO] Concatenated scene + montage for {ctx.job_id}", flush=True)
        else:
            shutil.copy2(montage_path, base_path)
            print(f"[VIDEO] Using montage segment as base for {ctx.job_id}", flush=True)

        if base_path.exists():
            trim_params: list[dict] = []
            segments_path = job_dir / "montage_segments.json"
            if segments_path.exists():
                try:
                    trim_params = json.loads(segments_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, KeyError, TypeError):
                    pass
            self._inject_av_alignment(ctx, job_dir, base_path, trim_params)
            return [self._to_artifact("video_base", base_path, workspace_dir)]

        print(f"[VIDEO WARN] base.mp4 not produced for {ctx.job_id}", flush=True)
        return []

    def _inject_av_alignment(
        self,
        ctx: PhaseContext,
        job_dir: Path,
        base_path: Path,
        trim_params: list[dict],
    ) -> None:
        """Shift TTS audio + subtitles to the montage start and persist the
        authoritative Final Timeline (issue #179).

        The scene segment occupies ``[0, scene_ms)`` with no voice/subtitle;
        the montage (voice + subtitle) is offset by ``scene_ms``.  Produces
        ``audio_aligned.mp3``, ``subtitles_offset.srt`` and ``final_timeline.json``
        next to ``base.mp4``.  On alignment failure the original audio is kept
        and the timeline is marked ``aligned: false`` (best-effort render).
        """
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        scene_path = job_dir / "scene_segment.mp4"
        if not audio_path.exists() or not trim_params:
            return

        scene_ms = compute_scene_offset_ms(scene_path)
        base_ms = int(round(self._get_media_duration(base_path) * 1000))

        aligned = True
        # 1. Offset TTS audio to the montage start, sized to the base length.
        try:
            align_audio(
                audio_path,
                job_dir / "audio_aligned.mp3",
                offset_ms=scene_ms,
                total_ms=base_ms,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort alignment
            aligned = False
            print(f"[VIDEO WARN] audio align failed, using original: {exc}", flush=True)

        # 2. Offset subtitles by the same scene duration (if present).
        if srt_path.exists():
            shifted = shift_srt(srt_path.read_text(encoding="utf-8"), scene_ms)
            (job_dir / "subtitles_offset.srt").write_text(shifted, encoding="utf-8")

        # 3. Persist the authoritative Final Timeline (render-time, no dir scan).
        timeline = build_final_timeline(
            scene_ms=scene_ms,
            montage_segments=trim_params,
            aligned=aligned,
        )
        (job_dir / "final_timeline.json").write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # Rerender changed the Final Timeline — any prior export is now stale (#180).
        try:
            from packages.pipeline_services.export_task import ExportTaskService

            ExportTaskService(
                job_id=ctx.job_id,
                job_dir=job_dir,
                workspace_dir=ctx.project_dir.parent,
                project_dir=ctx.project_dir,
                export_dir=ctx.project_dir / "runtime" / "exports",
            ).mark_stale()
        except Exception:  # noqa: BLE001 — never block rendering on export cleanup
            pass
        print(
            f"[VIDEO] Final Timeline: scene_ms={scene_ms} aligned={aligned} "
            f"segments={len(timeline['segments'])} fp={timeline['fingerprint'][:8]}",
            flush=True,
        )

    # -- final_rendering handler ---------------------------------------------

    def _run_final_rendering(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """final_rendering: burn subtitles, music, cover title into final video.

        Reads settings from the job JSON file (written by the UI) rather than
        ``ctx.options``, since that is where the UI persists them.
        """
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"
        final_path = job_dir / "final.mp4"
        base_path = job_dir / "base.mp4"
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        job_json_path = ctx.project_dir / "control" / "jobs" / f"{ctx.job_id}.json"

        skip_subtitle = False
        music_path: Path | None = None
        music_volume = 80
        cover_title_data: dict | None = None

        if job_json_path.exists():
            job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
            skip_subtitle = job_data.get("skip_subtitle", False)
            music_track = job_data.get("music_track_path", "")
            music_volume = job_data.get("music_volume", 80)
            ct = job_data.get("cover_title")
            if ct and ct.get("text"):
                cover_title_data = ct
            if music_track:
                music_path = ctx.root_dir / music_track
                if not music_path.exists():
                    music_path = None

        actual_srt_path = None if skip_subtitle else srt_path
        # Prefer AV-aligned audio + offset subtitles produced by video_rendering
        # (issue #179): TTS/subtitle shifted to the montage start.
        aligned_audio = job_dir / "audio_aligned.mp3"
        offset_srt = job_dir / "subtitles_offset.srt"
        if aligned_audio.exists():
            audio_path = aligned_audio
        if not skip_subtitle and offset_srt.exists():
            actual_srt_path = offset_srt
        cond = (
            f"base={base_path.exists()} audio={audio_path.exists()}"
            f" skip_subtitle={skip_subtitle} srt={srt_path.exists()}"
        )
        print(f"[FINAL] {ctx.job_id}: {cond}", flush=True)
        if (
            base_path.exists()
            and audio_path.exists()
            and (skip_subtitle or srt_path.exists())
        ):
            self._video_svc.burn_final_video(
                base_path,
                audio_path,
                actual_srt_path,
                final_path,
                cover_clip_path=None,
                cover_title=cover_title_data,
                music_path=music_path,
                music_volume=music_volume,
            )

        if final_path.exists():
            print(
                f"[FINAL] {ctx.job_id}: final.mp4 produced ({final_path.stat().st_size} bytes)",
                flush=True,
            )
            return [self._to_artifact("final_video", final_path, workspace_dir)]
        print(f"[FINAL] {ctx.job_id}: final.mp4 NOT produced", flush=True)
        return []

    # -- final_review handler (pure gate) ------------------------------------

    def _run_final(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """final_review: pure gate — no handler logic.  Burn happens in final_rendering."""
        return []

    # -- scene_assembling handler (import mode) --------------------------------

    def _run_scene_assembly(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """scene_assembling: build scene segment from scene folders with crossfade transitions.

        Reads scene folder paths from ``ctx.scene_folder_paths`` (populated by
        the tick service) or falls back to ``ctx.scene_config`` or ConfigReader.
        Picks one random video file from each folder, then uses ffmpeg ``xfade``
        to create a crossfade scene segment.
        """
        import random

        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)

        # 1. Resolve scene folder paths
        folders = self._resolve_scene_folders(ctx)

        if not folders:
            print(f"[SCENE] No scene folders configured for {ctx.job_id}", flush=True)
            return []

        # 2. Check for existing snapshot (deterministic re-render, Issue #174)
        import json as _json
        import shutil as _shutil

        snapshot_dir = job_dir / ".scene_snapshot"
        manifest_path = snapshot_dir / "manifest.json"
        force_reselect: bool = ctx.options.get("force_reselect", False)
        clips: list[Path] = []

        if manifest_path.exists() and not force_reselect:
            # Verify source file fingerprints per-entry (issue #227 / #174 AC-6)
            manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
            valid_entries: list[int] = []  # indices whose fingerprint still matches
            invalid_entries: list[int] = []  # indices whose source has changed
            for idx, entry in enumerate(manifest):
                src = Path(entry["source"])
                if src.exists():
                    st = src.stat()
                    if st.st_size == entry["size"] and st.st_mtime == entry["mtime"]:
                        valid_entries.append(idx)
                    else:
                        # ponytail: mtime-based fingerprint; content hash if drift
                        invalid_entries.append(idx)
                else:
                    # missing source = snapshot still valid (we have the local copy)
                    valid_entries.append(idx)

            if invalid_entries:
                print(
                    f"[SCENE] {len(invalid_entries)}/{len(manifest)} source fingerprints "
                    f"changed, re-randomizing only those entries",
                    flush=True,
                )

            for idx in valid_entries:
                local_path = snapshot_dir / manifest[idx]["local"]
                if local_path.exists():
                    clips.append(local_path)

            # Re-randomize only the invalidated entries from their source folders
            if invalid_entries:
                for idx in invalid_entries:
                    if idx < len(folders) and folders[idx].exists():
                        candidates = self._scene_candidates(folders[idx])
                        if candidates:
                            clips.insert(idx, random.choice(candidates))
                        else:
                            # Fallback: use existing snapshot even if stale
                            local_path = snapshot_dir / manifest[idx]["local"]
                            if local_path.exists():
                                clips.insert(idx, local_path)
                    else:
                        local_path = snapshot_dir / manifest[idx]["local"]
                        if local_path.exists():
                            clips.insert(idx, local_path)

            if clips:
                print(
                    f"[SCENE] Using snapshot ({len(valid_entries)} cached + "
                    f"{len(invalid_entries)} re-randomized)",
                    flush=True,
                )

            # Update snapshot for re-randomized entries
            if invalid_entries:
                snapshot_dir.mkdir(parents=True, exist_ok=True)
                for idx in invalid_entries:
                    if idx < len(clips):
                        clip = clips[idx]
                        local_name = f"{idx}{clip.suffix}"
                        _shutil.copy2(clip, snapshot_dir / local_name)
                        st = clip.stat()
                        found = False
                        for entry in manifest:
                            if entry["local"] == manifest[idx]["local"]:
                                entry.update(
                                    {
                                        "source": str(clip.resolve()),
                                        "local": local_name,
                                        "size": st.st_size,
                                        "mtime": st.st_mtime,
                                    }
                                )
                                found = True
                                break
                        if not found:
                            manifest.append(
                                {
                                    "source": str(clip.resolve()),
                                    "local": local_name,
                                    "size": st.st_size,
                                    "mtime": st.st_mtime,
                                }
                            )
                (snapshot_dir / "manifest.json").write_text(
                    _json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

        if not clips:
            # Fully fresh selection: every entry was invalid or no manifest
            for folder in folders:
                if not folder.exists():
                    print(f"[SCENE] Folder not found: {folder}", flush=True)
                    continue
                candidates = self._scene_candidates(folder)
                if not candidates:
                    print(f"[SCENE] No video files in {folder}", flush=True)
                    continue
                clips.append(random.choice(candidates))

            if not clips:
                print(f"[SCENE] No clips found for {ctx.job_id}", flush=True)
                return []

            print(f"[SCENE] {len(clips)} clips selected for {ctx.job_id}", flush=True)
            for c in clips:
                print(f"[SCENE]   {c}", flush=True)

            # Snapshot: copy selected clips to job-owned .scene_snapshot/
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            manifest = []
            for i, clip in enumerate(clips):
                local_name = f"{i}{clip.suffix}"
                _shutil.copy2(clip, snapshot_dir / local_name)
                st = clip.stat()
                manifest.append(
                    {
                        "source": str(clip.resolve()),
                        "local": local_name,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                    }
                )
            (snapshot_dir / "manifest.json").write_text(
                _json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(
                f"[SCENE] Snapshot saved: {len(manifest)} clips → {snapshot_dir}",
                flush=True,
            )

        transition_duration = ctx.transition_duration_ms / 1000.0
        scene_path = job_dir / "scene_segment.mp4"

        if len(clips) == 1:
            # Single clip -- copy directly
            import shutil

            shutil.copy2(clips[0], scene_path)
            print(f"[SCENE] Single clip copied to {scene_path}", flush=True)
        else:
            # Build ffmpeg xfade chain
            ffmpeg = self._get_ffmpeg_path()
            durations = [self._get_media_duration(c) for c in clips]

            # Filter chain: settb on all inputs, then chained xfade
            filter_parts: list[str] = []
            accumulated = durations[0]
            for i in range(1, len(clips)):
                offset = accumulated - transition_duration
                prev_label = f"r{i - 1}" if i > 1 else "c0"
                cur_in_label = f"c{i}"
                out_label = f"t{i}"

                # Build segments
                filter_parts.append(
                    f"[{i}:v]settb=AVTB,fps=30,scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2[{cur_in_label}]"
                )
                filter_parts.append(
                    f"[{prev_label}][{cur_in_label}]"
                    f"xfade=transition=fade:duration={transition_duration:.3f}:"
                    f"offset={offset:.3f}[{out_label}]"
                )
                if i < len(clips) - 1:
                    filter_parts.append(
                        f"[{out_label}]setpts=PTS-STARTPTS,fps=30[r{i}]"
                    )

                accumulated += durations[i] - transition_duration

            # First input always needs settb + fps + scale normalization
            filter_complex = (
                "[0:v]settb=AVTB,fps=30,scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2[c0];"
                + ";".join(filter_parts)
            )
            final_label = f"t{len(clips) - 1}"

            cmd = [ffmpeg, "-y"]
            for clip in clips:
                cmd.extend(["-i", str(clip)])
            cmd.extend(
                [
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    f"[{final_label}]",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "ultrafast",
                    "-crf",
                    "23",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(scene_path),
                ]
            )

            print(f"[SCENE] Running ffmpeg xfade for {len(clips)} clips", flush=True)
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)

        if scene_path.exists():
            print(
                f"[SCENE] scene_segment.mp4 produced ({scene_path.stat().st_size} bytes)",
                flush=True,
            )
            return [self._to_artifact("scene_segment", scene_path, workspace_dir)]
        return []

    def _resolve_scene_folders(self, ctx: PhaseContext) -> list[Path]:
        folders: list[Path] = []
        if ctx.scene_folder_paths:
            for folder_path in ctx.scene_folder_paths:
                path = Path(folder_path)
                if not path.is_absolute():
                    path = ctx.root_dir / "workspace" / path
                folders.append(path)
            return folders

        scene_config = ctx.scene_config
        if not scene_config and self._config is not None:
            scene_config = self._config.get_scene_config(product_id=ctx.product)
        for entry in scene_config.get("folders", []):
            path_str = entry.get("path", "")
            if path_str:
                folders.append(ctx.root_dir / "workspace" / path_str)
        return folders

    @staticmethod
    def _scene_candidates(folder: Path) -> list[Path]:
        if not folder.exists() or not folder.is_dir():
            return []
        video_ext = {".mp4", ".mov", ".avi"}
        return [
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in video_ext
        ]

    def _load_montage_inputs(
        self, ctx: PhaseContext
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], ExecutionFailure | None]:
        """Load and validate the immutable inputs for ``montage_assembling``.

        Returns (selected_clips, sentence_timing_dicts, error).  The same
        checks are used by ``validate_phase_input`` and ``_run_montage_assembly``
        so the pre-execution contract and runtime contract cannot drift.
        """
        job_dir = self._job_dir(ctx)
        audio_path = job_dir / "audio.mp3"
        snapshot_path = job_dir / "reviewed_assets.json"
        sentences_path = job_dir / "sentences.json"

        if not snapshot_path.exists():
            return (
                [],
                [],
                ExecutionFailure(
                    code="MONTAGE_SNAPSHOT_MISSING",
                    message=(
                        "The reviewed asset snapshot is missing; "
                        "asset review must be approved first."
                    ),
                    retryable=False,
                ),
            )
        if not audio_path.exists():
            return (
                [],
                [],
                ExecutionFailure(
                    code="MONTAGE_AUDIO_MISSING",
                    message="TTS audio is required before the montage can be assembled.",
                    retryable=False,
                ),
            )
        if not sentences_path.exists():
            return (
                [],
                [],
                ExecutionFailure(
                    code="MONTAGE_TIMINGS_MISSING",
                    message=(
                        "Sentence timings are required before the montage can be assembled."
                    ),
                    retryable=False,
                ),
            )

        try:
            selected = json.loads(snapshot_path.read_text(encoding="utf-8"))
            sentence_timings = [
                t.model_dump() for t in self._discover_sentence_timings(job_dir)
            ]
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            return (
                [],
                [],
                ExecutionFailure(
                    code="MONTAGE_INPUT_INVALID",
                    message=f"Montage input is invalid: {exc}",
                    retryable=False,
                ),
            )

        if not selected:
            return (
                [],
                [],
                ExecutionFailure(
                    code="MONTAGE_DECISIONS_MISSING",
                    message=(
                        "At least one reviewed asset decision is required to build the montage."
                    ),
                    retryable=False,
                ),
            )

        unresolved = [c for c in selected if c.get("visual_type") == "unresolved"]
        if unresolved:
            return (
                [],
                [],
                ExecutionFailure(
                    code="MONTAGE_UNRESOLVED_DECISIONS",
                    message=(
                        f"{len(unresolved)} reviewed asset decision(s) are still unresolved."
                    ),
                    retryable=False,
                ),
            )

        missing = [
            c
            for c in selected
            if c.get("visual_type") == "clip"
            and c.get("file_path")
            and not Path(c["file_path"]).exists()
        ]
        if missing:
            return (
                [],
                [],
                ExecutionFailure(
                    code="MONTAGE_CLIP_FILE_MISSING",
                    message=f"Reviewed clip file not found: {missing[0].get('file_path', '')}",
                    retryable=False,
                ),
            )

        return selected, sentence_timings, None

    # -- montage_assembling handler (generate + import modes) ------------------

    def _run_montage_assembly(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """montage_assembling: build the independent Montage Segment.

        Consumes the immutable ``reviewed_assets.json`` snapshot, the TTS audio,
        and canonical sentence timings to produce ``montage_segment.mp4`` plus
        the authoritative ``montage_segments.json`` trim-parameter manifest.

        A missing snapshot/audio/timings, unresolved decisions, or missing clip
        files are raised as structured failures by the shared input loader.
        """
        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)
        selected, sentence_timings, error = self._load_montage_inputs(ctx)
        if error is not None:
            # Validation should have caught this, but if it didn't, raise so
            # execute_phase converts it into a structured MEDIA_INPUT_INVALID.
            raise ValueError(error.message)

        audio_path = job_dir / "audio.mp3"
        montage_path = job_dir / "montage_segment.mp4"
        segments_path = job_dir / "montage_segments.json"

        trim_params = self._video_svc.build_base_video(
            ctx.project_dir,
            {
                "job_id": ctx.job_id,
                "asset_bundle": {
                    "audio_path": str(audio_path),
                    "selected_clips": selected,
                },
                "sequence": 1,
            },
            montage_path,
            sentence_timings=sentence_timings if sentence_timings else None,
        )
        if trim_params is None:
            trim_params = []

        if not montage_path.exists():
            print(
                f"[MONTAGE] build_base_video did not produce {montage_path}",
                flush=True,
            )
            return []

        segments_path.write_text(
            json.dumps(trim_params, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        result: list[ArtifactPointer] = []
        if montage_path.exists():
            result.append(
                self._to_artifact("montage_segment", montage_path, workspace_dir)
            )
        if segments_path.exists():
            result.append(
                self._to_artifact("montage_segments", segments_path, workspace_dir)
            )
        return result

    @staticmethod
    def _discover_script(job_dir: Path) -> str | None:
        """Return the script text from *口播文案.txt or *口播文案.json, or None."""
        for p in job_dir.glob("*口播文案.txt"):
            return p.read_text(encoding="utf-8").strip() or None
        for p in job_dir.glob("*口播文案.json"):
            jdata = json.loads(p.read_text(encoding="utf-8"))
            text = jdata.get("text", "").strip()
            return text or None
        return None

    @staticmethod
    def _discover_sentence_timings(job_dir: Path) -> list[SentenceTiming]:
        """Return sentence timings from sentences.json if present and valid."""
        path = job_dir / "sentences.json"
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return [SentenceTiming.model_validate(item) for item in data]
        except Exception as exc:  # noqa: BLE001
            print(
                f"[TTS TIMING WARN] Failed to load sentence timings: {exc}", flush=True
            )
            return []

    # -- ffmpeg helpers (lazy imports) -----------------------------------------

    @staticmethod
    def _get_ffmpeg_path() -> str:
        """Resolve ffmpeg path via media_utils."""
        from packages.pipeline_services.media_utils import get_ffmpeg_path as _gfp

        return _gfp()

    @staticmethod
    def _get_media_duration(file_path: Path) -> float:
        """Get media duration in seconds via ffprobe."""
        from packages.pipeline_services.media_utils import get_media_duration as _gmd

        return _gmd(file_path)


def _fallback_category_suggestion_model() -> str:
    """Fallback: return the default category suggestion model."""
    return "deepseek-v4-flash"
