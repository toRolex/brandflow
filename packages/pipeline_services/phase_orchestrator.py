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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from packages.domain_core.models import ArtifactPointer
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge
from packages.pipeline_services.media_compositor import MediaCompositor
from packages.pipeline_services.script_service.generator import ScriptGenerator
from packages.pipeline_services.subtitle_service import SubtitleService
from packages.pipeline_services.video_service import VideoService
from packages.provider_config.config_resolver import ConfigResolver
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore


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

    *config_reader* is required — all config reads go through a ConfigResolver
    wrapping it.
    """
    from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge
    from packages.pipeline_services.subtitle_service import SubtitleService
    from packages.pipeline_services.video_service import VideoService

    return PhaseOrchestrator(
        script_bridge=LegacyScriptBridge(root_dir),
        subtitle_svc=SubtitleService(),
        video_svc=VideoService(dry_run=False),
        config_resolver=ConfigResolver(reader=config_reader),
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
        script_bridge: LegacyScriptBridge,
        subtitle_svc: SubtitleService,
        video_svc: VideoService,
        *,
        schedule_store: Any = None,
        config_reader: ConfigReader | None = None,
        secret_store: SecretStore | None = None,
        config_resolver: ConfigResolver | None = None,
        get_tts_config: Callable[[], dict[str, Any]] | None = None,
        get_llm_config: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._script_bridge = script_bridge
        self._subtitle_svc = subtitle_svc
        self._video_svc = video_svc
        self._schedule_store = schedule_store
        self._config = config_reader
        self._secrets = secret_store if secret_store is not None else SecretStore()
        self._get_tts_config = get_tts_config
        self._get_llm_config = get_llm_config

        # High-level config resolver: preferred path for all config queries.
        if config_resolver is not None:
            self._config_resolver = config_resolver
        elif config_reader is not None:
            self._config_resolver = ConfigResolver(
                reader=config_reader, secrets=self._secrets
            )
        else:
            self._config_resolver = None

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

    def run_phases_parallel(
        self, phases: list[str], ctx: PhaseContext
    ) -> dict[str, list[ArtifactPointer]]:
        """Execute multiple phases concurrently via ``ThreadPoolExecutor``.

        Each phase runs its registered handler. Failures propagate to the
        caller so the state machine can mark the job as failed.

        Returns
        -------
        dict[str, list[ArtifactPointer]]
            Mapping from phase name to its produced artifacts.
        """
        results: dict[str, list[ArtifactPointer]] = {}

        with ThreadPoolExecutor(max_workers=len(phases)) as executor:
            future_map = {
                executor.submit(self.run_phase, phase, ctx): phase for phase in phases
            }
            for future in as_completed(future_map):
                phase_name = future_map[future]
                results[phase_name] = future.result()

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

    # -- config resolution helpers (internal delegates to ConfigResolver) --

    def _resolve_tts_config(self, ctx: PhaseContext) -> dict[str, Any]:
        """Resolve TTS config via ConfigResolver (internal delegate)."""
        if self._config_resolver is not None:
            return self._config_resolver.tts(product_id=ctx.product)
        if self._get_tts_config is not None:
            return self._get_tts_config()
        raise RuntimeError(
            "No ConfigResolver or TTS config callback available; "
            "create_orchestrator() requires a ConfigReader"
        )

    def _resolve_llm_config(self, ctx: PhaseContext) -> dict[str, Any]:
        """Resolve LLM config via ConfigResolver (internal delegate)."""
        if self._config_resolver is not None:
            return self._config_resolver.llm(product_id=ctx.product)[0]
        if self._get_llm_config is not None:
            return self._get_llm_config()
        raise RuntimeError(
            "No ConfigResolver or LLM config callback available; "
            "create_orchestrator() requires a ConfigReader"
        )

    def _resolve_api_key(self, llm_config: dict[str, Any]) -> str:
        """Resolve API key via ConfigResolver (internal delegate)."""
        if self._config_resolver is not None:
            provider = llm_config.get("provider", "deepseek")
            return self._config_resolver._api_key_for(provider)
        provider = llm_config.get("provider", "deepseek")
        return self._secrets.get_api_key(provider)

    def _resolve_api_url(self, llm_config: dict[str, Any]) -> str:
        """Resolve chat-completions URL via ConfigResolver (internal delegate)."""
        if self._config_resolver is not None:
            provider = llm_config.get("provider", "deepseek")
            return self._config_resolver._chat_completions_url_for(provider)
        provider = llm_config.get("provider", "deepseek")
        url = self._secrets.get_api_base_url(provider)
        if url and not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        return url

    def _resolve_categories(self, ctx: PhaseContext) -> list[str]:
        """Resolve category names for asset classification via ConfigResolver.

        Priority: product-level categories > asset_library categories > defaults.
        """
        if self._config_resolver is not None:
            return self._config_resolver.categories(product_id=ctx.product)

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
            script_result = self._script_bridge.generate(
                product=ctx.product,
                output_dir=job_dir,
                mock=False,
                language=language,
                brand=ctx.brand,
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
            if not src_audio.exists():
                raise FileNotFoundError(f"Uploaded audio not found: {src_audio}")
            shutil.copy2(src_audio, audio_path)
            print(f"[TTS] Using uploaded audio: {src_audio}", flush=True)
        else:
            existing_script = self._discover_script(job_dir)
            print(
                f"[TTS DEBUG] phase=tts_generating, script_found={existing_script is not None}, "
                f"len={len(existing_script) if existing_script else 0}",
                flush=True,
            )
            if not existing_script:
                raise RuntimeError(f"No script text found in {job_dir}")

            tts_cfg = self._resolve_tts_config(ctx)

            # Apply job-level TTS overrides (tts_model / tts_voice)
            # Priority: job override > provider defaults > global/product config
            job_tts_model: str = ctx.options.get("tts_model", "")
            job_tts_voice: str = ctx.options.get("tts_voice", "")
            if job_tts_model:
                tts_cfg["model"] = job_tts_model
            if job_tts_voice:
                tts_cfg["voice"] = job_tts_voice

            config = _TTSConfigShim(tts_cfg)
            tts_provider = self._build_tts_provider(tts_cfg)
            audio_bytes = tts_provider.synthesize(existing_script, config)
            audio_path.write_bytes(audio_bytes)
            print(
                f"[TTS] Synthesized: {audio_path.exists()}, "
                f"size={audio_path.stat().st_size if audio_path.exists() else 0}",
                flush=True,
            )

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

    def _run_subtitle(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """subtitle_generating: build SRT from audio + script text."""
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        print(
            f"[SUBTITLE] audio exists={audio_path.exists()}, srt exists={srt_path.exists()}",
            flush=True,
        )
        if not audio_path.exists():
            raise FileNotFoundError(f"audio.mp3 not found in {job_dir}")
        script_text = self._discover_script(job_dir) or ""
        print(
            f"[SUBTITLE] script found={bool(script_text)}, len={len(script_text)}",
            flush=True,
        )
        if script_text:
            try:
                self._subtitle_svc.build_srt(audio_path, srt_path, script_text)
                print(f"[SUBTITLE] srt generated={srt_path.exists()}", flush=True)
            except Exception as e:
                print(f"[SUBTITLE ERROR] {type(e).__name__}: {e}", flush=True)
                import traceback

                traceback.print_exc()
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

        from packages.file_store.paths import shared_asset_db_path
        from packages.pipeline_services.asset_library import (
            AssetRepository,
            AssetRetriever,
        )
        from packages.pipeline_services.asset_library.classify import create_classify_fn

        db_path = shared_asset_db_path(ctx.root_dir)

        llm_config = self._resolve_llm_config(ctx)

        api_key = self._resolve_api_key(llm_config)
        api_url = self._resolve_api_url(llm_config)

        classify_fn = None
        if api_key and api_url:
            category_names = self._resolve_categories(ctx)
            category_model = (
                self._config.get_category_suggestion_model()
                if self._config is not None
                else _fallback_category_suggestion_model()
            )

            classify_fn = create_classify_fn(
                api_url=api_url,
                api_key=api_key,
                model=category_model,
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
        """video_rendering: compose base video for final rendering.

        In import mode:
          1. Build a clip-based montage video from ``audio.mp3`` and
             ``selected_clips.json``.
          2. Concatenate ``assembled.mp4`` (scene segment from
             ``montage_assembling``) with the clip-based video → ``base.mp4``.

        In generate mode, builds base video from clips directly (no
        ``assembled.mp4`` expected to exist).

        Falls back gracefully when one or both sources are missing.
        """
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"
        audio_path = job_dir / "audio.mp3"
        clip_list_path = job_dir / "selected_clips.json"
        base_path = job_dir / "base.mp4"
        assembled_path = job_dir / "assembled.mp4"

        # -- Step 1: build clip-based montage video ---------------------------
        clip_base_path = job_dir / "_clip_base.mp4"
        clip_base_built = False

        if audio_path.exists() and clip_list_path.exists():
            selected = json.loads(clip_list_path.read_text(encoding="utf-8"))
            selected = [item for item in selected if Path(item["file_path"]).exists()]

            if selected:
                self._video_svc.build_base_video(
                    ctx.project_dir,
                    {
                        "job_id": ctx.job_id,
                        "asset_bundle": {
                            "audio_path": str(audio_path),
                            "selected_clips": selected,
                        },
                        "sequence": 1,
                    },
                    clip_base_path,
                )
                clip_base_built = clip_base_path.exists()

        # -- Step 2: compose final base.mp4 ------------------------------------
        assembled_exists = assembled_path.exists()

        if assembled_exists and clip_base_built:
            # Import mode: concat scene segment + montage clips
            MediaCompositor.concat_two(assembled_path, clip_base_path, base_path)
            print(
                f"[VIDEO] Concatenated assembled + clip base for {ctx.job_id}",
                flush=True,
            )
        elif clip_base_built:
            # Generate mode (or import mode without assembled.mp4 yet)
            shutil.copy2(clip_base_path, base_path)
            print(
                f"[VIDEO] Using clip-based video as base for {ctx.job_id}",
                flush=True,
            )
        elif assembled_exists:
            # Import mode fallback: scene segment only, no clips available
            shutil.copy2(assembled_path, base_path)
            print(
                f"[VIDEO] Using assembled video as base for {ctx.job_id} (no clips)",
                flush=True,
            )
        else:
            print(
                f"[VIDEO WARN] Neither assembled.mp4 nor clip base produced"
                f" for {ctx.job_id}",
                flush=True,
            )

        # Clean up temp clip base
        if clip_base_path.exists():
            clip_base_path.unlink()

        if base_path.exists():
            return [self._to_artifact("video_base", base_path, workspace_dir)]
        print(f"[VIDEO WARN] base.mp4 not produced for {ctx.job_id}", flush=True)
        return []

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
        folders: list[Path] = []
        if ctx.scene_folder_paths:
            for fp in ctx.scene_folder_paths:
                p = Path(fp)
                if not p.is_absolute():
                    p = ctx.root_dir / "workspace" / p
                folders.append(p)
        else:
            # Fallback: ctx.scene_config > ConfigReader
            scene_config = ctx.scene_config
            if not scene_config and self._config is not None:
                scene_config = self._config.get_scene_config(product_id=ctx.product)
            for entry in scene_config.get("folders", []):
                path_str = entry.get("path", "")
                if not path_str:
                    continue
                p = ctx.root_dir / "workspace" / path_str
                folders.append(p)

        if not folders:
            print(f"[SCENE] No scene folders configured for {ctx.job_id}", flush=True)
            return []

        # 2. Pick one random video from each folder
        video_ext = {".mp4", ".mov", ".avi"}
        clips: list[Path] = []
        for folder in folders:
            if not folder.exists():
                print(f"[SCENE] Folder not found: {folder}", flush=True)
                continue
            candidates = [
                p
                for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() in video_ext
            ]
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

        transition_duration = ctx.transition_duration_ms / 1000.0
        scene_path = job_dir / "scene_segment.mp4"

        if len(clips) == 1:
            # Single clip -- copy directly
            import shutil

            shutil.copy2(clips[0], scene_path)
            print(f"[SCENE] Single clip copied to {scene_path}", flush=True)
        else:
            MediaCompositor.crossfade_scene(clips, scene_path, transition_duration)
            print(f"[SCENE] Running ffmpeg xfade for {len(clips)} clips", flush=True)

        if scene_path.exists():
            print(
                f"[SCENE] scene_segment.mp4 produced ({scene_path.stat().st_size} bytes)",
                flush=True,
            )
            return [self._to_artifact("scene_segment", scene_path, workspace_dir)]
        return []

    # -- montage_assembling handler (import mode) ------------------------------

    def _run_montage_assembly(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """montage_assembling: merge scene segment + base video into assembled video.

        Reads ``scene_segment.mp4`` from the scene_assembling phase and
        ``base.mp4`` (if present, e.g. from a previous generate-mode run).
        Concatenates them into ``assembled.mp4`` which ``_run_video`` then uses
        as the base video in import mode.

        If only one of the two files exists it is used directly; if neither
        exists the handler returns an empty list.
        """
        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)
        scene_path = job_dir / "scene_segment.mp4"
        base_path = job_dir / "base.mp4"
        assembled_path = job_dir / "assembled.mp4"

        scene_exists = scene_path.exists()
        base_exists = base_path.exists()

        if scene_exists and base_exists:
            print(
                f"[MONTAGE] Concatenating scene_segment + base for {ctx.job_id}",
                flush=True,
            )
            MediaCompositor.concat_two(scene_path, base_path, assembled_path)
        elif scene_exists:
            print(
                f"[MONTAGE] Using scene_segment as assembled for {ctx.job_id}",
                flush=True,
            )
            shutil.copy2(scene_path, assembled_path)
        elif base_exists:
            print(
                f"[MONTAGE] Using base as assembled for {ctx.job_id}",
                flush=True,
            )
            shutil.copy2(base_path, assembled_path)
        else:
            print(
                f"[MONTAGE] Neither scene_segment nor base found for {ctx.job_id}",
                flush=True,
            )
            return []

        if assembled_path.exists():
            print(
                f"[MONTAGE] assembled.mp4 produced ({assembled_path.stat().st_size} bytes)",
                flush=True,
            )
            return [self._to_artifact("assembled_video", assembled_path, workspace_dir)]
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


def _fallback_category_suggestion_model() -> str:
    """Fallback: return the default category suggestion model."""
    return "deepseek-v4-flash"
