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
from packages.pipeline_services.subtitle_service import SubtitleService
from packages.pipeline_services.video_service import VideoService
from packages.pipeline_services.tts_provider import MiMoTTSProvider
from packages.provider_config.app_config import AppConfigManager
from apps.control_plane.services.schedule_store import ScheduleStore
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge
from packages.pipeline_services.phase_orchestrator import PhaseContext, PhaseOrchestrator


REVIEW_PHASES = {"script_review", "tts_review", "asset_review", "final_review"}
AUTO_TICK_INTERVAL = 3  # seconds between auto-advances in dev mode


def _to_url_path(path: Path, workspace_dir: Path) -> str:
    """Convert a workspace-relative Path to a URL-safe forward-slash path."""
    return path.relative_to(workspace_dir).as_posix()


def _phase_to_artifacts(phase: str, job_id: str, project_dir: Path, root_dir: Path, product: str, manual_script: str = "", uploaded_audio_path: str = "") -> list[dict]:
    """DEPRECATED — all branches migrated to PhaseOrchestrator.

    Kept temporarily for reference.  All callers now use ``orchestrator.run_phase()``.
    Will be removed in Task 8 (cleanup).
    """
    return []


async def _auto_tick(root_dir: Path):
    """Dev-mode background loop: scans disk for non-review jobs, generates stub artifacts, and advances them."""
    # Construct orchestrator once; deps are stateless, reused across iterations
    app_config = AppConfigManager()
    tts_cfg = app_config.get_tts_config()
    tts_model = tts_cfg.get("model", "mimo-v2.5-tts") or ""
    if tts_model.startswith("qwen"):
        from packages.pipeline_services.tts_provider import QwenTTSProvider
        tts_provider = QwenTTSProvider(
            api_key=app_config.get_api_key("qwen"),
            base_url=app_config.get_api_base_url("qwen") or "https://dashscope.aliyuncs.com/api/v1",
        )
    else:
        tts_provider = MiMoTTSProvider(
            api_key=app_config.get_api_key("mimo"),
            base_url=app_config.get_api_base_url("mimo") or "https://api.xiaomimimo.com/v1",
        )
    orchestrator = PhaseOrchestrator(
        script_bridge=LegacyScriptBridge(root_dir),
        subtitle_svc=SubtitleService(),
        video_svc=VideoService(dry_run=False),
        tts_provider=tts_provider,
        schedule_store=ScheduleStore(root_dir),
        get_tts_config=app_config.get_tts_config,
        get_llm_config=app_config.get_llm_config,
    )

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
                                print(f"[AUTO-TICK] {job_id}: auto_approved {current} -> {data['phase']}", flush=True)
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
                            print(f"[AUTO-TICK] {job_id}: skip subtitle_generating -> {data['phase']}", flush=True)
                            continue

                        # Execute real pipeline for the target phase
                        product = data.get("product", os.environ.get("PRODUCT", "荔枝菌"))
                        manual_script = data.get("manual_script", "")
                        uploaded_audio_path = data.get("uploaded_audio_path", "")

                        ctx = PhaseContext(
                            job_id=job_id,
                            project_dir=project_dir,
                            root_dir=root_dir,
                            product=product,
                            options={
                                "manual_script": manual_script,
                                "uploaded_audio_path": uploaded_audio_path,
                            },
                        )
                        artifacts = [
                            a.model_dump()
                            for a in orchestrator.run_phase(target, ctx)
                        ]

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
                        elif target == "video_rendering":
                            # Video rendering failure: retry once, then mark as failed
                            if "video_rendering" in data.get("last_error", ""):
                                data["phase"] = "failed"
                                print(f"[AUTO-TICK] {job_id}: video_rendering failed after retry, marking as failed", flush=True)
                            else:
                                print(f"[AUTO-TICK] {job_id}: video_rendering produced no artifacts, will retry next tick", flush=True)
                                data["last_error"] = "video_rendering failed to produce artifacts"
                        elif target == "subtitle_generating":
                            # Critical phase: do NOT auto-advance on failure
                            # Stay in current phase and log the error
                            print(f"[AUTO-TICK] {job_id}: {target} produced no artifacts, staying in phase", flush=True)
                            data["last_error"] = f"{target} failed to produce artifacts"
                        else:
                            # No artifacts produced - auto-advance (transitional phase or error)
                            try:
                                data["phase"] = next_phase(target)
                            except ValueError:
                                data["phase"] = "completed"

                        f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                        print(f"[AUTO-TICK] {job_id}: {current} -> {data['phase']} (artifacts: {[a['kind'] for a in artifacts]})", flush=True)

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
