import asyncio
import json
import os
import time

from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.control_plane._version import get_version as _get_version

from apps.control_plane.routes.api_assets import router as api_assets_router
from apps.control_plane.routes.api_jobs import router as api_jobs_router
from apps.control_plane.routes.api_projects import router as api_projects_router
from apps.control_plane.routes.category_suggestion import (
    router as category_suggestion_router,
)
from apps.control_plane.routes.config import router as config_router
from apps.control_plane.routes.reviews import router as reviews_router
from apps.control_plane.routes.workers import router as workers_router
from apps.control_plane.routes.tts import router as tts_router
from apps.control_plane.routes.metrics import router as metrics_router
from apps.control_plane.routes.knowledge import router as knowledge_router
from apps.control_plane.routes.templates import router as templates_router
from apps.control_plane.routes.products import router as products_router
from apps.control_plane.routes.version_check import router as version_check_router
from apps.control_plane.routes.version_check import (
    _read_progress,
    _cleanup_progress,
    _reset_update_lock,
    _is_stalled,
    _STARTUP_RESET_SECONDS,
)
from apps.control_plane.services.dispatch import Dispatcher
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import (
    JobTickService,
    PhaseExecutionError,
)
from packages.pipeline_services.phase_orchestrator import create_orchestrator
from packages.provider_config.config_reader import ConfigReader, ProductStore
from packages.provider_config.secret_store import SecretStore


AUTO_TICK_INTERVAL = 3  # seconds between auto-advances in dev mode


async def _auto_tick(root_dir: Path, config_reader: ConfigReader):
    """Dev-mode background loop: offloads tick to executor, respects single-in-flight.

    Each ``tick()`` call is dispatched through ``run_in_executor`` so the
    event loop stays free for API requests during blocking work (FFmpeg,
    TTS/LLM network calls).  A set of in-flight job ids prevents the
    outer scan from re-picking a job that is still executing.
    """
    orchestrator = create_orchestrator(root_dir, config_reader=config_reader)
    repo = FileStoreRepository(root_dir)
    tick_svc = JobTickService(
        orchestrator=orchestrator,
        repo=repo,
        config_reader=config_reader,
        sleep_fn=time.sleep,
    )
    _in_flight: set[str] = set()

    while True:
        await asyncio.sleep(AUTO_TICK_INTERVAL)
        try:
            projects_root = root_dir / "workspace" / "projects"
            if not projects_root.exists():
                continue

            for project_dir in sorted(projects_root.iterdir()):
                if not project_dir.is_dir():
                    continue
                project_id = project_dir.name
                jobs_dir = project_dir / "control" / "jobs"
                if not jobs_dir.exists():
                    continue

                for f in sorted(jobs_dir.glob("*.json")):
                    try:
                        data = json.loads(f.read_text(encoding="utf-8"))
                        job_id = data.get("job_id", "")
                        if not job_id:
                            continue

                        # Single-in-flight guard: skip jobs already being
                        # processed.  Currently defensive — each tick is awaited
                        # before the next job iteration, so the set never holds
                        # more than one entry.  It is kept as a safety net for
                        # future concurrency changes (e.g. fan-out scheduling).
                        if job_id in _in_flight:
                            continue

                        product = data.get("product", os.environ.get("PRODUCT", ""))
                        options = {
                            "manual_script": data.get("manual_script", ""),
                            "uploaded_audio_path": data.get("uploaded_audio_path", ""),
                            "language": data.get("language", "mandarin"),
                            "mode": data.get("mode", "generate"),
                        }

                        _in_flight.add(job_id)
                        try:
                            loop = asyncio.get_running_loop()

                            def _tick_job():
                                return tick_svc.tick(
                                    project_id,
                                    job_id,
                                    product,
                                    root_dir=root_dir,
                                    project_dir=project_dir,
                                    options=options,
                                )

                            summary = await loop.run_in_executor(None, _tick_job)
                        finally:
                            _in_flight.discard(job_id)

                        if summary.action != "skipped":
                            print(
                                f"[AUTO-TICK] {job_id}: {summary.from_phase} -> {summary.to_phase} ({summary.action})",
                                flush=True,
                            )
                    except PhaseExecutionError as e:
                        print(
                            f"[AUTO-TICK] {e.job_id}: {e.phase} phase failed: {e}",
                            flush=True,
                        )
                    except Exception as e:
                        print(f"[AUTO-TICK ERROR] {f.name}: {e}", flush=True)
                        import traceback

                        traceback.print_exc()
        except Exception as e:
            print(f"[AUTO-TICK LOOP ERROR] {e}", flush=True)
            import traceback

            traceback.print_exc()


def _startup_cleanup_progress() -> None:
    """On startup: clean up stale progress.json and reset the in-memory lock.

    - running/restarting older than 5 min → reset _update_in_progress + delete progress.json
    - done/failed → delete progress.json (no lock to reset)
    """
    progress = _read_progress()
    if progress is None:
        return

    status = progress.get("status", "")
    updated_at = progress.get("updated_at", "")

    if status in ("running", "restarting"):
        if _is_stalled(updated_at, _STARTUP_RESET_SECONDS):
            _reset_update_lock()
            _cleanup_progress()

    if status in ("done", "failed"):
        _cleanup_progress()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup: clean up stale progress.json ──
    _startup_cleanup_progress()

    dev_mode = os.environ.get("DEV_AUTO_TICK", "1") == "1"
    auto_tick_task: asyncio.Task[None] | None = None
    if dev_mode:
        auto_tick_task = asyncio.create_task(
            _auto_tick(app.state.root_dir, app.state.config_reader),
            name="brandflow-auto-tick",
        )
        app.state.auto_tick_task = auto_tick_task
    try:
        yield
    finally:
        if auto_tick_task is not None:
            auto_tick_task.cancel()
            with suppress(asyncio.CancelledError):
                await auto_tick_task

        shutdown = getattr(app.state.export_executor, "shutdown", None)
        if shutdown is not None:
            shutdown(wait=False, cancel_futures=True)


def _get_orchestrator(app: FastAPI):
    orchestrator = getattr(app.state, "orchestrator", None)
    if orchestrator is None:
        orchestrator = create_orchestrator(
            app.state.root_dir, config_reader=app.state.config_reader
        )
        app.state.orchestrator = orchestrator
    return orchestrator


def create_app(root_dir: Path | None = None) -> FastAPI:
    app = FastAPI(title="Brandflow Control Plane", lifespan=lifespan)

    allow_origins_env = os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:17890",
    )
    allow_origins = [o.strip() for o in allow_origins_env.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.root_dir = root_dir or Path.cwd()
    app.state.dispatcher = Dispatcher(FileStoreRepository(app.state.root_dir))
    config_dir = app.state.root_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    reader = ConfigReader(config_dir=str(config_dir))
    app.state.config_reader = reader
    app.state.orchestrator = None
    app.state.product_store = ProductStore(
        reader=reader, config_path=config_dir / "app_config.json"
    )
    app.state.secret_store = SecretStore()

    # Background executor for export tasks (#180). EXPORT_SYNC=1 runs inline —
    # deterministic for tests and single-process dev.
    if os.environ.get("EXPORT_SYNC", "0") == "1":
        from concurrent.futures import Future

        class _SyncExecutor:
            def submit(self, fn, *args, **kwargs):
                fut: Future = Future()
                try:
                    fut.set_result(fn(*args, **kwargs))
                except Exception as exc:  # noqa: BLE001
                    fut.set_exception(exc)
                return fut

        app.state.export_executor = _SyncExecutor()
    else:
        from concurrent.futures import ThreadPoolExecutor

        app.state.export_executor = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="export"
        )
    app.include_router(api_assets_router)
    app.include_router(api_projects_router)
    app.include_router(api_jobs_router)
    app.include_router(category_suggestion_router)
    app.include_router(config_router)
    app.include_router(workers_router)
    app.include_router(reviews_router)
    app.include_router(tts_router)
    app.include_router(metrics_router)
    app.include_router(knowledge_router)
    app.include_router(templates_router)
    app.include_router(products_router)
    app.include_router(version_check_router)

    @app.get("/api/health")
    async def health(deploy_check: bool = False):
        from packages.deploy_health.checker import DeployHealthChecker

        result: dict = {"status": "ok", "version": _get_version()}
        if deploy_check:
            checker = DeployHealthChecker(root_dir=app.state.root_dir)
            health_result = checker.check_all()
            result["deploy_health"] = health_result.to_dict()
            if health_result.overall != "healthy":
                result["status"] = "degraded"
                result["deploy_health"]["overall"] = health_result.overall
        return result

    workspace = root_dir or Path.cwd() / "workspace"
    if workspace.exists():
        app.mount("/workspace", StaticFiles(directory=str(workspace)), name="workspace")

    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(frontend_dist / "assets")),
            name="assets",
        )

        @app.get("/{full_path:path}")
        async def serve_spa(request: Request, full_path: str):
            file_path = frontend_dist / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(frontend_dist / "index.html")

    return app
