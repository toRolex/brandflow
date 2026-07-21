from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from apps.control_plane.routes.jobs.helpers import (
    _export_service,
    _find_job_project,
    _read_final_timeline_fingerprint,
    _run_export_task,
)
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


@router.post("/jobs/{job_id}/export", status_code=202)
def create_export(request: Request, job_id: str):
    """Create (or reuse) a durable background export task; returns its id.

    Does not block on the ZIP — the bundle builds in the background. Poll
    ``GET .../export/status`` and download via ``GET .../export/download``.
    """
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    record = repo.load_job(project_id, job_id)
    if record.phase != "completed":
        raise HTTPException(status_code=400, detail="job not yet completed")

    fingerprint = _read_final_timeline_fingerprint(request, project_id, job_id)
    if not fingerprint:
        raise HTTPException(
            status_code=409,
            detail="no Final Timeline; rerender required before export",
        )

    service = _export_service(request, project_id, job_id)
    task = service.create_or_reuse(fingerprint)
    if task["status"] == "queued":
        executor = request.app.state.export_executor
        executor.submit(_run_export_task, service, task["task_id"])
    return {"task_id": task["task_id"], "status": task["status"]}


@router.get("/jobs/{job_id}/export/status")
def export_status(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    service = _export_service(request, project_id, job_id)
    service.recover_interrupted()
    task = service._load()
    if not task:
        raise HTTPException(status_code=404, detail="no export task")
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "progress": task["progress"],
        "error": task.get("error"),
    }


@router.get("/jobs/{job_id}/export/download")
def download_export(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    service = _export_service(request, project_id, job_id)
    service.recover_interrupted()
    task = service._load()
    if not task or task["status"] != "ready":
        raise HTTPException(status_code=409, detail="export not ready")

    zip_path = Path(task["zip_path"])
    if not zip_path.exists():
        raise HTTPException(status_code=409, detail="export not ready")
    return FileResponse(
        zip_path, media_type="application/zip", filename=f"export_{job_id}.zip"
    )


@router.post("/jobs/{job_id}/export/invalidate")
def invalidate_export(request: Request, job_id: str):
    """Mark the current export task stale (called on rerender)."""
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    service = _export_service(request, project_id, job_id)
    service.mark_stale()
    return {"status": "stale"}
