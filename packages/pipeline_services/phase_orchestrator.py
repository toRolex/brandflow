"""PhaseOrchestrator — executes pipeline phases and returns ArtifactPointer lists.

This module extracts the logic from ``app._phase_to_artifacts`` (285-line god function)
into small, testable, injectable handler methods.

Slice 1: ``script_generating`` only.  Subsequent slices migrate remaining phases.
Slice 2: ``tts_generating``.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.domain_core.models import ArtifactPointer
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge
from packages.pipeline_services.script_service.generator import ScriptGenerator
from packages.pipeline_services.subtitle_service import SubtitleService
from packages.pipeline_services.video_service import VideoService
from packages.provider_config.app_config import AppConfigManager


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def to_url_path(path: Path, workspace_dir: Path) -> str:
    """Convert a workspace-relative *Path* to a URL-safe forward-slash string."""
    return path.relative_to(workspace_dir).as_posix()


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
    options: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PhaseOrchestrator
# ---------------------------------------------------------------------------

class PhaseOrchestrator:
    """Strategy-map dispatcher: one handler per phase, injected dependencies."""

    def __init__(
        self,
        script_bridge: LegacyScriptBridge,
        subtitle_svc: SubtitleService,
        video_svc: VideoService,
        tts_provider: Any,
        schedule_store: Any,
        get_tts_config: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._script_bridge = script_bridge
        self._subtitle_svc = subtitle_svc
        self._video_svc = video_svc
        self._tts_provider = tts_provider
        self._schedule_store = schedule_store
        self._get_tts_config = get_tts_config

        self._handlers: dict[str, Callable[[PhaseContext], list[ArtifactPointer]]] = {
            "script_generating": self._run_script,
            "tts_generating": self._run_tts,
            "tts_review": self._run_tts_review,
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

    # -- script_generating handler ------------------------------------------

    def _run_script(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute script generation (manual or LLM) and optional cover title."""
        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)
        manual_script: str = ctx.options.get("manual_script", "")
        result: list[ArtifactPointer] = []

        # 1. Generate or write script
        if manual_script:
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
            script_result = self._script_bridge.generate(
                product=ctx.product, output_dir=job_dir, mock=False,
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
        self, ctx: PhaseContext, script_result: dict[str, Any],
    ) -> None:
        """Auto-generate cover title if the job JSON has no ``cover_title.text``.

        This is the ONE place a handler reads config directly — because cover
        title generation is self-contained and not worth a separate dependency.
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

            app_config = AppConfigManager()
            llm_config = app_config.get_llm_config()

            class _CoverConfig:
                api_key = app_config.get_llm_api_key()
                base_url = app_config.get_llm_endpoint()
                model = llm_config.get("model", "deepseek-v4-pro")

            gen = ScriptGenerator(_CoverConfig())
            cover_title = gen.generate_cover_title(script_text, ctx.product, "滋元堂")
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
        """Execute TTS synthesis or copy uploaded audio.

        Discovery order for uploaded audio:
            1. ``ctx.options["uploaded_audio_path"]`` → copy file directly
            2. Otherwise discover script text from ``*口播文案.txt`` then ``*.json``
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
                try:
                    get_tts_config = self._get_tts_config
                    if get_tts_config is None:
                        app_config = AppConfigManager()
                        get_tts_config = app_config.get_tts_config
                    tts_cfg = get_tts_config()

                    config = _TTSConfigShim(tts_cfg)
                    audio_bytes = self._tts_provider.synthesize(existing_script, config)
                    audio_path.write_bytes(audio_bytes)
                    print(
                        f"[TTS] Synthesized: {audio_path.exists()}, "
                        f"size={audio_path.stat().st_size if audio_path.exists() else 0}",
                        flush=True,
                    )
                except Exception as e:
                    print(f"[TTS ERROR] {type(e).__name__}: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[TTS WARN] No script text found in {job_dir}", flush=True)

        if audio_path.exists():
            result.append(self._to_artifact("tts_audio", audio_path, workspace_dir))

        return result

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
