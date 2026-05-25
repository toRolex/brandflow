import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.control_plane.routes.api_jobs import router as api_jobs_router
from apps.control_plane.routes.api_projects import router as api_projects_router
from apps.control_plane.routes.api_schedule import router as api_schedule_router
from apps.control_plane.routes.config import router as config_router
from apps.control_plane.routes.jobs import router as jobs_router
from apps.control_plane.routes.projects import router as projects_router
from apps.control_plane.routes.reviews import router as reviews_router
from apps.control_plane.routes.workers import router as workers_router
from apps.control_plane.services.dispatch import Dispatcher
from packages.domain_core.state import next_phase, PHASE_ORDER
from packages.file_store.repository import FileStoreRepository

REVIEW_PHASES = {"script_review", "asset_review", "final_review"}
AUTO_TICK_INTERVAL = 8  # seconds between auto-advances in dev mode


async def _auto_tick(dispatcher: Dispatcher, root_dir: Path):
    """Dev-mode background loop: auto-advances jobs through non-review phases."""
    repo = FileStoreRepository(root_dir)
    while True:
        await asyncio.sleep(AUTO_TICK_INTERVAL)
        try:
            # Process queued tasks from the dispatcher queue
            while dispatcher.queue:
                task = dispatcher.queue[0]
                project_id = task.project_id
                job_id = task.job_id

                try:
                    record = repo.load_job(project_id, job_id)
                except Exception:
                    dispatcher.queue.pop(0)
                    continue

                current = record.phase
                if current == "queued":
                    # Move to first execution phase
                    next_p = "script_generating"
                elif current in REVIEW_PHASES:
                    # Stop at review gates — don't auto-approve
                    dispatcher.queue.pop(0)
                    continue
                elif current == "completed" or current in ("failed", "cancelled", "paused"):
                    dispatcher.queue.pop(0)
                    continue
                else:
                    try:
                        next_p = next_phase(current)
                    except ValueError:
                        next_p = "completed"

                # If next is a review gate, stop there
                if next_p in REVIEW_PHASES:
                    record = record.model_copy(update={
                        "phase": next_p,
                        "review_status": "pending",
                    })
                else:
                    record = record.model_copy(update={"phase": next_p})

                repo.save_job(project_id, record)
                repo.append_review_event(project_id, {
                    "job_id": job_id,
                    "event": "auto_tick",
                    "from_phase": current,
                    "to_phase": record.phase,
                })
                dispatcher.queue.pop(0)
        except Exception:
            pass  # Silently skip errors in auto-tick


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    dev_mode = os.environ.get("DEV_AUTO_TICK", "1") == "1"
    if dev_mode:
        asyncio.create_task(_auto_tick(app.state.dispatcher, app.state.root_dir))
    yield
    # Shutdown — nothing to clean up


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
    app.include_router(api_projects_router)
    app.include_router(api_jobs_router)
    app.include_router(api_schedule_router)
    app.include_router(projects_router)
    app.include_router(config_router)
    app.include_router(workers_router)
    app.include_router(jobs_router)
    app.include_router(reviews_router)

    frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

    return app
