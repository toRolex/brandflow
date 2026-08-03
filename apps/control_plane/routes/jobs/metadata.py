from __future__ import annotations

from fastapi import APIRouter, Request

from apps.control_plane.routes.jobs.helpers import _resolve_job_project
from apps.control_plane.services.music_library import MusicLibrary
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


@router.get("/jobs/{job_id}/logs")
def get_job_logs(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _resolve_job_project(repo, job_id)
    record = repo.load_job(project_id, job_id)
    log_path = repo.layout.job_log_path(project_id, job_id)
    try:
        logs = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
    except OSError:
        logs = ""
    return {"logs": logs or record.last_error or "", "job_id": job_id}


@router.get("/music")
def list_music(request: Request):
    lib = MusicLibrary(request.app.state.root_dir)
    return {"tracks": lib.tracks}
