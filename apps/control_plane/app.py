import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.control_plane.routes.api_assets import router as api_assets_router
from apps.control_plane.routes.api_jobs import router as api_jobs_router
from apps.control_plane.routes.api_projects import router as api_projects_router
from apps.control_plane.routes.api_schedule import router as api_schedule_router
from apps.control_plane.routes.config import router as config_router
from apps.control_plane.routes.jobs import router as jobs_router
from apps.control_plane.routes.projects import router as projects_router
from apps.control_plane.routes.reviews import router as reviews_router
from apps.control_plane.routes.workers import router as workers_router
from apps.control_plane.routes.tts import router as tts_router
from apps.control_plane.services.dispatch import Dispatcher
from packages.domain_core.state import next_phase
from packages.file_store.paths import shared_asset_db_path
from packages.pipeline_services.subtitle_service import SubtitleService
from packages.pipeline_services.video_service import VideoService
from packages.pipeline_services.tts_provider import MiMoTTSProvider, QwenTTSProvider
from packages.provider_config.app_config import AppConfigManager
from apps.control_plane.services.schedule_store import ScheduleStore
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge


REVIEW_PHASES = {"script_review", "tts_review", "asset_review", "final_review"}
AUTO_TICK_INTERVAL = 3  # seconds between auto-advances in dev mode


def _to_url_path(path: Path, workspace_dir: Path) -> str:
    """Convert a workspace-relative Path to a URL-safe forward-slash path."""
    return path.relative_to(workspace_dir).as_posix()


def _phase_to_artifacts(phase: str, job_id: str, project_dir: Path, root_dir: Path, product: str, manual_script: str = "", uploaded_audio_path: str = "") -> list[dict]:
    """Execute the real pipeline for the target phase and return artifact pointers."""
    print(f"[PHASE] target={phase}, job={job_id}", flush=True)
    workspace_dir = root_dir / "workspace"
    job_dir = project_dir / "runtime" / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict] = []
    script_bridge = LegacyScriptBridge(root_dir)
    subtitle_svc = SubtitleService()
    video_svc = VideoService(dry_run=False)
    schedule_store = ScheduleStore(root_dir)

    if phase == "script_generating":
        if manual_script:
            txt_path = job_dir / "口播文案.txt"
            txt_path.write_text(manual_script, encoding="utf-8")
            json_path = job_dir / "口播文案.json"
            json_path.write_text(json.dumps({"text": manual_script, "source": "manual"}, ensure_ascii=False), encoding="utf-8")
            script_result = {"txt_path": str(txt_path), "json_path": str(json_path), "final_script": manual_script}
        else:
            script_result = script_bridge.generate(product=product, output_dir=job_dir, mock=False)
        txt_path = Path(script_result["txt_path"])
        json_path = Path(script_result["json_path"])
        for p in [txt_path, json_path]:
            if p.exists():
                rel = _to_url_path(p, workspace_dir)
                result.append({"kind": "script", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": p.stat().st_size})

    elif phase == "tts_generating":
        audio_path = job_dir / "audio.mp3"
        if uploaded_audio_path:
            src_audio = root_dir / uploaded_audio_path
            if src_audio.exists():
                import shutil
                shutil.copy2(src_audio, audio_path)
                print(f"[TTS] Using uploaded audio: {src_audio}", flush=True)
            else:
                print(f"[TTS WARN] Uploaded audio not found: {src_audio}", flush=True)
        else:
            existing_script = None
            for a in job_dir.glob("*口播文案.txt"):
                existing_script = a.read_text(encoding="utf-8").strip()
                break
            if not existing_script:
                for a in job_dir.glob("*口播文案.json"):
                    jdata = json.loads(a.read_text(encoding="utf-8"))
                    existing_script = jdata.get("text", "").strip()
                    break
            print(f"[TTS DEBUG] phase=tts_generating, script_found={existing_script is not None}, len={len(existing_script) if existing_script else 0}", flush=True)
            if existing_script:
                try:
                    app_config = AppConfigManager()
                    tts_cfg = app_config.get_tts_config()

                    class _TTSConfig:
                        model = tts_cfg.get("model", "mimo-v2.5-tts")
                        voice = tts_cfg.get("voice", "Mia")
                        instructions = tts_cfg.get("instructions", "")
                        language_type = tts_cfg.get("language_type", "")
                        optimize_instructions = tts_cfg.get("optimize_instructions", False)
                        fallback_voice = tts_cfg.get("fallback_voice", "Dean")
                        randomize_voice = tts_cfg.get("randomize_voice", False)
                        random_voices = tts_cfg.get("random_voices", ["Mia", "Dean"])
                        style_control_mode = tts_cfg.get("style_control_mode", "simple")
                        style_prompt = tts_cfg.get("style_prompt", "自然 清晰")
                        voice_design_prompt = tts_cfg.get("voice_design_prompt", "")
                        audio_format = tts_cfg.get("audio_format", "wav")
                        audio_tags_enabled = tts_cfg.get("audio_tags_enabled", False)
                        audio_tags = tts_cfg.get("audio_tags", "")
                        voice_clone_sample_path = tts_cfg.get("voice_clone_sample_path", "")
                        voice_clone_mime_type = tts_cfg.get("voice_clone_mime_type", "")
                        optimize_text_preview = tts_cfg.get("optimize_text_preview", False)
                        director_character = tts_cfg.get("director_character", "")
                        director_scene = tts_cfg.get("director_scene", "")
                        director_guidance = tts_cfg.get("director_guidance", "")

                    model = _TTSConfig.model or ""
                    if model.startswith("qwen"):
                        api_key = app_config.get_api_key("qwen")
                        base_url = app_config.get_api_base_url("qwen") or "https://dashscope.aliyuncs.com/api/v1"
                        tts_provider = QwenTTSProvider(api_key=api_key, base_url=base_url)
                    else:
                        api_key = app_config.get_api_key("mimo")
                        base_url = app_config.get_api_base_url("mimo") or "https://api.xiaomimimo.com/v1"
                        tts_provider = MiMoTTSProvider(api_key=api_key, base_url=base_url)

                    audio_bytes = tts_provider.synthesize(existing_script, _TTSConfig())
                    audio_path.write_bytes(audio_bytes)
                    print(f"[TTS] Synthesized: {audio_path.exists()}, size={audio_path.stat().st_size if audio_path.exists() else 0}", flush=True)
                except Exception as e:
                    print(f"[TTS ERROR] {type(e).__name__}: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
            else:
                print(f"[TTS WARN] No script text found in {job_dir}", flush=True)
        if audio_path.exists():
            rel = _to_url_path(audio_path, workspace_dir)
            result.append({"kind": "tts_audio", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": audio_path.stat().st_size})

    elif phase == "tts_review":
        # TTS review phase: just return existing audio artifact for review
        audio_path = job_dir / "audio.mp3"
        if audio_path.exists():
            rel = _to_url_path(audio_path, workspace_dir)
            result.append({"kind": "tts_audio", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": audio_path.stat().st_size})
            print(f"[TTS_REVIEW] Audio ready for review: {audio_path}", flush=True)
        else:
            print(f"[TTS_REVIEW WARN] No audio found in {job_dir}", flush=True)

    elif phase == "subtitle_generating":
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        print(f"[SUBTITLE] audio exists={audio_path.exists()}, srt exists={srt_path.exists()}", flush=True)
        if audio_path.exists():
            script_text = ""
            for a in job_dir.glob("*口播文案.txt"):
                script_text = a.read_text(encoding="utf-8").strip()
                break
            print(f"[SUBTITLE] script found={bool(script_text)}, len={len(script_text)}", flush=True)
            if script_text:
                try:
                    subtitle_svc.build_srt(audio_path, srt_path, script_text)
                    print(f"[SUBTITLE] srt generated={srt_path.exists()}", flush=True)
                except Exception as e:
                    print(f"[SUBTITLE ERROR] {type(e).__name__}: {e}", flush=True)
                    import traceback
                    traceback.print_exc()
        else:
            print(f"[SUBTITLE WARN] audio.mp3 not found in {job_dir}", flush=True)
        if srt_path.exists():
            rel = _to_url_path(srt_path, workspace_dir)
            result.append({"kind": "subtitle", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": srt_path.stat().st_size})

    elif phase == "asset_retrieving":
        # Run semantic retrieval: script text → keyword match → selected clips
        script_text = ""
        for a in job_dir.glob("*口播文案.txt"):
            script_text = a.read_text(encoding="utf-8").strip()
            break

        if script_text:
            db_path = shared_asset_db_path(root_dir)

            from packages.pipeline_services.asset_library import AssetRepository, AssetRetriever
            from packages.pipeline_services.asset_library.classify import create_classify_fn

            app_config = AppConfigManager()
            llm_config = app_config.get_llm_config()
            api_key = app_config.get_api_key(llm_config.get("provider", "deepseek"))
            api_url = app_config.get_api_base_url(llm_config.get("provider", "deepseek"))

            classify_fn = None
            if api_key and api_url:
                if not api_url.endswith("/chat/completions"):
                    api_url = f"{api_url}/chat/completions"
                classify_fn = create_classify_fn(
                    api_url=api_url,
                    api_key=api_key,
                    model="deepseek-v4-flash",
                )

            repo = AssetRepository(db_path)
            retriever = AssetRetriever(repo, classify_fn=classify_fn)

            selected = retriever.retrieve(script_text, product)

            clip_list_path = job_dir / "selected_clips.json"
            clip_list_path.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")

            result.append({
                "kind": "selected_clips",
                "relative_path": _to_url_path(clip_list_path, workspace_dir),
                "url": f"/workspace/{_to_url_path(clip_list_path, workspace_dir)}",
                "size_bytes": clip_list_path.stat().st_size,
            })
        else:
            # No script text found — emit sentinel so auto_tick can advance
            result.append({
                "kind": "asset_retrieval_done",
                "relative_path": "",
                "url": "",
                "size_bytes": 0,
            })

    elif phase == "video_rendering":
        base_path = job_dir / "base.mp4"
        audio_path = job_dir / "audio.mp3"
        clip_list_path = job_dir / "selected_clips.json"

        if audio_path.exists() and clip_list_path.exists():
            selected = json.loads(clip_list_path.read_text(encoding="utf-8"))
            selected = [item for item in selected if Path(item["file_path"]).exists()]

            if selected:
                base_path = job_dir / "base.mp4"
                video_svc.build_base_video(
                    project_dir,
                    {
                        "job_id": job_id,
                        "asset_bundle": {"audio_path": str(audio_path), "selected_clips": selected},
                        "sequence": 1,
                    },
                    base_path,
                )

        if base_path.exists():
            rel = _to_url_path(base_path, workspace_dir)
            result.append({"kind": "video_base", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": base_path.stat().st_size})

    elif phase == "final_review":
        final_path = job_dir / "final.mp4"
        base_path = job_dir / "base.mp4"
        audio_path = job_dir / "audio.mp3"
        srt_path = job_dir / "subtitles.srt"
        job_json_path = project_dir / "control" / "jobs" / f"{job_id}.json"
        skip_subtitle = False
        if job_json_path.exists():
            job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
            skip_subtitle = job_data.get("skip_subtitle", False)
        actual_srt_path = None if skip_subtitle else srt_path
        if base_path.exists() and audio_path.exists() and (skip_subtitle or srt_path.exists()):
            video_svc.burn_final_video(
                base_path,
                audio_path,
                actual_srt_path,
                final_path,
                cover_clip_path=None,
            )
        if final_path.exists():
            rel = _to_url_path(final_path, workspace_dir)
            result.append({"kind": "final_video", "relative_path": rel, "url": f"/workspace/{rel}", "size_bytes": final_path.stat().st_size})
            # Also write to schedule
            job_json_path = project_dir / "control" / "jobs" / f"{job_id}.json"
            platform = ""
            if job_json_path.exists():
                job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
                platform = job_data.get("platform", "")
            schedule_store.add(job_id=job_id, platform=platform, title=product, description="")

    return result


async def _auto_tick(root_dir: Path):
    """Dev-mode background loop: scans disk for non-review jobs, generates stub artifacts, and advances them."""
    while True:
        await asyncio.sleep(AUTO_TICK_INTERVAL)
        try:
            projects_root = root_dir / "workspace" / "projects"
            if not projects_root.exists():
                continue

            for project_dir in sorted(projects_root.iterdir()):
                if not project_dir.is_dir():
                    continue
                jobs_dir = project_dir / "control" / "jobs"
                if not jobs_dir.exists():
                    continue

                for f in sorted(jobs_dir.glob("*.json")):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        job_id = data.get("job_id", "")
                        current = data.get("phase", "")

                        if not job_id:
                            continue
                        if current in ("completed", "failed", "cancelled", "paused"):
                            continue
                        # Skip review gates that are already pending approval (not yet approved)
                        if current in REVIEW_PHASES and data.get("review_status") not in ("approved",):
                            if data.get("auto_approve", False):
                                try:
                                    data["phase"] = next_phase(current)
                                except ValueError:
                                    data["phase"] = "completed"
                                data["review_status"] = "approved"
                                f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                                print(f"[AUTO-TICK] {job_id}: auto_approved {current} -> {data['phase']}")
                                continue
                            continue

                        # Process the current phase, then advance if artifacts are produced
                        # or if the phase produces no artifacts (auto-advance to next phase)
                        if current == "queued":
                            target = "script_generating"
                        else:
                            target = current

                        if current == "subtitle_generating" and data.get("skip_subtitle", False):
                            data["phase"] = next_phase("subtitle_generating")
                            f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                            print(f"[AUTO-TICK] {job_id}: skip subtitle_generating -> {data['phase']}")
                            continue

                        # Execute real pipeline for the target phase
                        product = data.get("product", os.environ.get("PRODUCT", "荔枝菌"))
                        manual_script = data.get("manual_script", "")
                        uploaded_audio_path = data.get("uploaded_audio_path", "")
                        artifacts = _phase_to_artifacts(target, job_id, project_dir, root_dir, product, manual_script, uploaded_audio_path)

                        # Merge artifacts (keep existing, add new ones)
                        existing = data.get("artifacts", [])
                        existing_kinds = {a.get("kind") for a in existing}
                        for a in artifacts:
                            if a["kind"] not in existing_kinds:
                                existing.append(a)
                        data["artifacts"] = existing

                        # Advance to next phase after processing current one
                        # Only advance one phase per auto_tick iteration
                        if target in REVIEW_PHASES:
                            data["phase"] = target
                            data["review_status"] = "pending"
                        elif artifacts:
                            # Artifacts produced, advance to next phase
                            try:
                                data["phase"] = next_phase(target)
                            except ValueError:
                                data["phase"] = "completed"
                        elif target in ("subtitle_generating", "video_rendering"):
                            # Critical phases: do NOT auto-advance on failure
                            # Stay in current phase and log the error
                            print(f"[AUTO-TICK] {job_id}: {target} produced no artifacts, staying in phase")
                            data["last_error"] = f"{target} failed to produce artifacts"
                        else:
                            # No artifacts produced - auto-advance (transitional phase or error)
                            try:
                                data["phase"] = next_phase(target)
                            except ValueError:
                                data["phase"] = "completed"

                        f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        print(f"[AUTO-TICK] {job_id}: {current} -> {data['phase']} (artifacts: {[a['kind'] for a in artifacts]})")

                        review_path = project_dir / "reviews" / "review_events.jsonl"
                        review_path.parent.mkdir(parents=True, exist_ok=True)
                        with review_path.open("a", encoding="utf-8") as h:
                            h.write(json.dumps({
                                "job_id": job_id,
                                "event": "auto_tick",
                                "from_phase": current,
                                "to_phase": data["phase"],
                            }, ensure_ascii=False) + "\n")
                    except Exception as e:
                        print(f"[AUTO-TICK ERROR] {f.name}: {e}")
                        import traceback
                        traceback.print_exc()
        except Exception as e:
            print(f"[AUTO-TICK LOOP ERROR] {e}")
            import traceback
            traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    dev_mode = os.environ.get("DEV_AUTO_TICK", "1") == "1"
    if dev_mode:
        asyncio.create_task(_auto_tick(app.state.root_dir))
    yield


def create_app(root_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Ziyuantang Control Plane", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.dispatcher = Dispatcher()
    app.state.root_dir = root_dir or Path.cwd()
    app.include_router(api_assets_router)
    app.include_router(api_projects_router)
    app.include_router(api_jobs_router)
    app.include_router(api_schedule_router)
    app.include_router(projects_router)
    app.include_router(config_router)
    app.include_router(workers_router)
    app.include_router(jobs_router)
    app.include_router(reviews_router)
    app.include_router(tts_router)

    workspace = root_dir or Path.cwd() / "workspace"
    if workspace.exists():
        app.mount("/workspace", StaticFiles(directory=str(workspace)), name="workspace")

    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            file_path = frontend_dist / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(frontend_dist / "index.html")

    return app
