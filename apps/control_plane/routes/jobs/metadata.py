from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.jobs.helpers import _find_job_project
from apps.control_plane.services.music_library import MusicLibrary
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


@router.get("/jobs/{job_id}/logs")
def get_job_logs(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    return {"logs": record.last_error or "", "job_id": job_id}


@router.get("/music")
def list_music(request: Request):
    lib = MusicLibrary(request.app.state.root_dir)
    return {"tracks": lib.tracks}
