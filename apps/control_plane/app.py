from fastapi import FastAPI

from apps.control_plane.routes.jobs import router as jobs_router
from apps.control_plane.routes.projects import router as projects_router
from apps.control_plane.routes.reviews import router as reviews_router
from apps.control_plane.routes.workers import router as workers_router
from apps.control_plane.services.dispatch import Dispatcher


def create_app() -> FastAPI:
    app = FastAPI(title="Ziyuantang Control Plane")
    app.state.dispatcher = Dispatcher()
    app.include_router(projects_router)
    app.include_router(workers_router)
    app.include_router(jobs_router)
    app.include_router(reviews_router)
    return app
