from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from packages.domain_core.models import JobRecord
from packages.domain_core.state import next_phase
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


class CreateJobRequest(BaseModel):
    product: str
    platforms: list[str]
    asset: str | None = None


class ReviewAction(BaseModel):
    review_gate: str


@router.post("/api/projects/{project_id}/jobs")
def create_job(request: Request, project_id: str, payload: CreateJobRequest):
    job_id = f"job_{payload.product}_{uuid4().hex[:8]}"
    dispatcher = request.app.state.dispatcher
    dispatcher.enqueue_demo_job(project_id, job_id)
    repo = FileStoreRepository(request.app.state.root_dir)
    repo.save_job(project_id, JobRecord(job_id=job_id, project_id=project_id, product=payload.product, phase="queued", review_status="none"))
    return {
        "job_id": job_id,
        "project_id": project_id,
        "product": payload.product,
        "platforms": payload.platforms,
        "phase": "queued",
        "review_status": "none",
        "artifacts": [],
    }


@router.get("/api/jobs/{job_id}")
def get_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    projects_root = repo.root / "workspace" / "projects"
    if projects_root.exists():
        for project_dir in projects_root.iterdir():
            if project_dir.is_dir():
                try:
                    record = repo.load_job(project_dir.name, job_id)
                    job_data = record.model_dump()
                    job_data["project_id"] = project_dir.name
                    return job_data
                except Exception:
                    continue
    raise HTTPException(status_code=404, detail="job not found")


@router.post("/api/jobs/{job_id}/pause")
def pause_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"phase": "paused"}))
    return {"status": "paused", "job_id": job_id}


@router.post("/api/jobs/{job_id}/retry")
def retry_job(request: Request, job_id: str):
    dispatcher = request.app.state.dispatcher
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"phase": "queued", "review_status": "none"}))
    dispatcher.enqueue_demo_job(project_id, job_id)
    return {"status": "queued_for_retry", "job_id": job_id}


@router.delete("/api/jobs/{job_id}")
def delete_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    repo.delete_job(project_id, job_id)
    return {"status": "deleted", "job_id": job_id}


@router.get("/api/jobs/{job_id}/logs")
def get_job_logs(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    return {"logs": record.last_error or "", "job_id": job_id}


def _find_job_project(repo: FileStoreRepository, job_id: str) -> str | None:
    projects_root = repo.root / "workspace" / "projects"
    if not projects_root.exists():
        return None
    for project_dir in projects_root.iterdir():
        if project_dir.is_dir():
            try:
                repo.load_job(project_dir.name, job_id)
                return project_dir.name
            except Exception:
                continue
    return None
