"""PhaseOrchestrator — executes pipeline phases and returns ArtifactPointer lists.

Each phase handler is a thin adapter: prepare inputs → call an injected seam
→ assemble artifact pointers.  All configuration resolution is delegated to the
injected ``ConfigResolver``; all media composition is delegated to the injected
``MediaCompositor``.

Supports **Generate** mode (LLM script → TTS → asset retrieval → video) and
**Import** mode (scene assembly + montage assembly with parallel TTS/subtitle).
"""

from __future__ import annotations

import json
import random
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Callable

from packages.domain_core.models import ArtifactPointer
from packages.pipeline_services.script_service import (
    build_generator_config,
    generate_cover_title,
    generate_script,
)
from packages.pipeline_services.script_service.generator import ScriptGenerator
from packages.pipeline_services.subtitle_service import SubtitleService
from packages.pipeline_services.tts_provider import TTSConfigShim, create_tts_provider
from packages.pipeline_services.video_service import VideoService
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
    """Factory: build a PhaseOrchestrator with real service dependencies."""
    secrets = SecretStore()
    script_generator = partial(generate_script, config_reader=config_reader, secret_store=secrets)

    return PhaseOrchestrator(
        script_generator=script_generator,
        subtitle_svc=SubtitleService(),
        video_svc=VideoService(dry_run=False),
        config_reader=config_reader,
        secret_store=secrets,
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
        script_generator: Callable[..., dict[str, Any]],
        subtitle_svc: SubtitleService,
        video_svc: VideoService,
        config_reader: ConfigReader,
        schedule_store: Any = None,
        secret_store: SecretStore | None = None,
    ) -> None:
        self._script_generator = script_generator
        self._subtitle_svc = subtitle_svc
        self._video_svc = video_svc
        self._schedule_store = schedule_store
        self._config = config_reader
        self._secrets = secret_store if secret_store is not None else SecretStore()

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

    # -- script_generating handler ------------------------------------------

    def _run_script(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """Execute script generation (manual or LLM) and optional cover title."""
        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)
        manual_script: str = ctx.options.get("manual_script", "")
        language = ctx.options.get("language", "mandarin")

        if manual_script:
            if language == "cantonese":
                manual_script = self._to_cantonese(manual_script, ctx)
            script_result = _write_manual_script(job_dir, manual_script)
        else:
            script_result = self._script_generator(
                product=ctx.product,
                output_dir=job_dir,
                language=language,
                brand=ctx.brand,
            )

        result = []
        for key in ("txt_path", "json_path"):
            p = Path(script_result[key])
            if p.exists():
                result.append(self._to_artifact("script", p, workspace_dir))

        self._maybe_generate_cover_title(ctx, script_result)
        return result

    def _to_cantonese(self, text: str, ctx: PhaseContext) -> str:
        """Convert *text* to Cantonese using the configured LLM."""
        try:
            gen = ScriptGenerator(
                build_generator_config(self._config, self._secrets, ctx.product)
            )
            converted = gen.to_cantonese(text, ctx.product, ctx.brand)
            print("[SCRIPT] Converted manual script to Cantonese", flush=True)
            return converted
        except Exception as e:
            print(
                f"[SCRIPT WARN] Cantonese conversion failed, using original: {e}",
                flush=True,
            )
            return text

    def _maybe_generate_cover_title(
        self,
        ctx: PhaseContext,
        script_result: dict[str, Any],
    ) -> None:
        """Auto-generate cover title if the job JSON has no ``cover_title.text``."""
        job_json_path = ctx.project_dir / "control" / "jobs" / f"{ctx.job_id}.json"
        if not job_json_path.exists():
            return

        job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
        existing_ct = job_data.get("cover_title", {})
        if existing_ct and existing_ct.get("text"):
            return

        script_text = script_result.get("final_script", "")
        txt_path = Path(script_result.get("txt_path", ""))
        if not script_text and txt_path.exists():
            script_text = txt_path.read_text(encoding="utf-8").strip()
        if not script_text:
            return

        try:
            cover_title = generate_cover_title(
                script_text, ctx.product, ctx.brand, self._config, self._secrets
            )
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
        """Execute TTS synthesis or copy uploaded audio."""
        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)
        audio_path = job_dir / "audio.mp3"
        uploaded_audio_path: str = ctx.options.get("uploaded_audio_path", "")

        if uploaded_audio_path:
            src_audio = ctx.root_dir / uploaded_audio_path
            if not src_audio.exists():
                raise FileNotFoundError(f"Uploaded audio not found: {src_audio}")
            shutil.copy2(src_audio, audio_path)
            print(f"[TTS] Using uploaded audio: {src_audio}", flush=True)
        else:
            existing_script = self._discover_script(job_dir)
            if not existing_script:
                raise RuntimeError(f"No script text found in {job_dir}")

            tts_cfg = self._config.get_tts_config(product_id=ctx.product)
            job_tts_model: str = ctx.options.get("tts_model", "")
            job_tts_voice: str = ctx.options.get("tts_voice", "")
            if job_tts_model:
                tts_cfg["model"] = job_tts_model
            if job_tts_voice:
                tts_cfg["voice"] = job_tts_voice

            provider = create_tts_provider(tts_cfg, self._secrets)
            audio_bytes = provider.synthesize(existing_script, TTSConfigShim(tts_cfg))
            audio_path.write_bytes(audio_bytes)
            print(
                f"[TTS] Synthesized: {audio_path.exists()}, "
                f"size={audio_path.stat().st_size if audio_path.exists() else 0}",
                flush=True,
            )

        return [self._to_artifact("tts_audio", audio_path, workspace_dir)]

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

    # -- subtitle_generating handler ----------------------------------------

    def _run_subtitle(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """subtitle_generating: build SRT from audio + script text."""
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        if not audio_path.exists():
            raise FileNotFoundError(f"audio.mp3 not found in {job_dir}")

        script_text = self._discover_script(job_dir) or ""
        if script_text:
            try:
                self._subtitle_svc.build_srt(audio_path, srt_path, script_text)
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
            return [ArtifactPointer(kind="asset_retrieval_done")]

        from packages.file_store.paths import shared_asset_db_path
        from packages.pipeline_services.asset_library import (
            AssetRepository,
            AssetRetriever,
        )
        from packages.pipeline_services.asset_library.classify import create_classify_fn

        db_path = shared_asset_db_path(ctx.root_dir)
        llm_cfg = self._config.get_llm_config(product_id=ctx.product)
        llm_provider = llm_cfg.get("provider", "deepseek")
        llm_api_key = self._secrets.get_api_key(llm_provider)
        llm_api_url = self._secrets.get_api_base_url(llm_provider)
        if llm_api_url and not llm_api_url.endswith("/chat/completions"):
            llm_api_url = f"{llm_api_url}/chat/completions"

        classify_fn = None
        if llm_api_key and llm_api_url:
            classify_fn = create_classify_fn(
                api_url=llm_api_url,
                api_key=llm_api_key,
                model=self._config.get_category_suggestion_model(),
                category_names=_resolve_categories(self._config, ctx),
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
        """video_rendering: compose base video for final rendering."""
        job_dir = self._job_dir(ctx)
        workspace_dir = ctx.root_dir / "workspace"
        audio_path = job_dir / "audio.mp3"
        clip_list_path = job_dir / "selected_clips.json"
        base_path = job_dir / "base.mp4"
        assembled_path = job_dir / "assembled.mp4"
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

        assembled_exists = assembled_path.exists()

        if assembled_exists and clip_base_built:
            self._media_compositor.concat_two(assembled_path, clip_base_path, base_path)
            print(
                f"[VIDEO] Concatenated assembled + clip base for {ctx.job_id}",
                flush=True,
            )
        elif clip_base_built:
            shutil.copy2(clip_base_path, base_path)
            print(
                f"[VIDEO] Using clip-based video as base for {ctx.job_id}", flush=True
            )
        elif assembled_exists:
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

        if clip_base_path.exists():
            clip_base_path.unlink()

        if base_path.exists():
            return [self._to_artifact("video_base", base_path, workspace_dir)]
        print(f"[VIDEO WARN] base.mp4 not produced for {ctx.job_id}", flush=True)
        return []

    # -- final_rendering handler ---------------------------------------------

    def _run_final_rendering(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """final_rendering: burn subtitles, music, cover title into final video."""
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
        """final_review: pure gate — no handler logic."""
        return []

    # -- scene_assembling handler (import mode) --------------------------------

    def _run_scene_assembly(self, ctx: PhaseContext) -> list[ArtifactPointer]:
        """scene_assembling: build scene segment from scene folders with crossfade transitions.

        Fallback: single clip is copied directly; zero clips returns an empty list.
        """
        workspace_dir = ctx.root_dir / "workspace"
        job_dir = self._job_dir(ctx)

        folders = _resolve_scene_folders(ctx)
        if not folders:
            print(f"[SCENE] No scene folders configured for {ctx.job_id}", flush=True)
            return []

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
        scene_path = job_dir / "scene_segment.mp4"

        if len(clips) == 1:
            shutil.copy2(clips[0], scene_path)
            print(f"[SCENE] Single clip copied to {scene_path}", flush=True)
        else:
            self._media_compositor.crossfade_scene(
                clips, scene_path, ctx.transition_duration_ms / 1000.0
            )
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

        ``concat_two`` normalises both inputs to 720x1280 before concatenation,
        so the output always matches the pipeline target spec regardless of input
        resolution.  Fallback: if only one of scene/base exists, it is copied
        directly (no normalisation applied).
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
            self._media_compositor.concat_two(scene_path, base_path, assembled_path)
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


# ---------------------------------------------------------------------------
# Module-level helpers (no instance state)
# ---------------------------------------------------------------------------


def _write_manual_script(job_dir: Path, text: str) -> dict[str, Any]:
    """Persist a manual script as txt/json artifacts and return a result dict."""
    txt_path = job_dir / "口播文案.txt"
    txt_path.write_text(text, encoding="utf-8")
    json_path = job_dir / "口播文案.json"
    json_path.write_text(
        json.dumps(
            {"text": text, "source": "manual"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return {
        "txt_path": str(txt_path),
        "json_path": str(json_path),
        "final_script": text,
    }


def _resolve_categories(config_reader: ConfigReader, ctx: PhaseContext) -> list[str]:
    """Resolve category names with priority: product > asset_library > defaults."""
    product_config = config_reader.get_product_config(product_id=ctx.product)
    product_cats = product_config.get("categories", [])
    if product_cats:
        return [c.get("name", "") for c in product_cats if c.get("name")]

    al_config = config_reader.get_asset_library_config()
    raw = al_config.get("categories", [])
    if raw:
        return [c.get("name", "") for c in raw if c.get("name")]

    # Default food categories
    return [
        "产地溯源", "原料展示", "加工过程", "质检品控",
        "包装仓储", "物流配送", "食用场景", "用户反馈",
        "品牌理念", "产品特写",
    ]


def _resolve_scene_folders(ctx: PhaseContext) -> list[Path]:
    """Resolve absolute scene folder paths from the phase context."""
    if ctx.scene_folder_paths:
        folders: list[Path] = []
        for fp in ctx.scene_folder_paths:
            p = Path(fp)
            if not p.is_absolute():
                p = ctx.root_dir / "workspace" / p
            folders.append(p)
        return folders

    folders = []
    for entry in ctx.scene_config.get("folders", []):
        path_str = entry.get("path", "")
        if not path_str:
            continue
        folders.append(ctx.root_dir / "workspace" / path_str)
    return folders
