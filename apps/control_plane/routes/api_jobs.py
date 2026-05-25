from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

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
    from uuid import uuid4

    job_id = f"job_{payload.product}_{uuid4().hex[:8]}"
    dispatcher = request.app.state.dispatcher
    dispatcher.enqueue_demo_job(project_id, job_id)
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
    # Try loading from all known projects since we don't know which project this job belongs to
    projects_root = repo.root / "workspace" / "projects"
    job_data = None
    if projects_root.exists():
        for project_dir in projects_root.iterdir():
            if project_dir.is_dir():
                try:
                    record = repo.load_job(project_dir.name, job_id)
                    job_data = record.model_dump()
                    job_data["project_id"] = project_dir.name
                    break
                except Exception:
                    continue
    if not job_data:
        return {
            "job_id": job_id,
            "project_id": "",
            "product": "",
            "platforms": [],
            "phase": "queued",
            "review_status": "none",
            "artifacts": [],
        }
    return job_data


@router.post("/api/jobs/{job_id}/pause")
def pause_job(request: Request, job_id: str):
    return {"status": "paused", "job_id": job_id}


@router.post("/api/jobs/{job_id}/retry")
def retry_job(request: Request, job_id: str):
    dispatcher = request.app.state.dispatcher
    # Find project by scanning workspace
    repo = FileStoreRepository(request.app.state.root_dir)
    projects_root = repo.root / "workspace" / "projects"
    project_id = ""
    if projects_root.exists():
        for project_dir in projects_root.iterdir():
            if project_dir.is_dir():
                try:
                    repo.load_job(project_dir.name, job_id)
                    project_id = project_dir.name
                    break
                except Exception:
                    continue
    if project_id:
        dispatcher.enqueue_demo_job(project_id, job_id)
    return {"status": "queued_for_retry", "job_id": job_id}


@router.get("/api/jobs/{job_id}/logs")
def get_job_logs(request: Request, job_id: str):
    return {"logs": "", "job_id": job_id}


@router.post("/api/reviews/{job_id}/approve")
def approve_review(request: Request, job_id: str, payload: ReviewAction):
    return {"status": "approved", "job_id": job_id, "gate": payload.review_gate}


@router.post("/api/reviews/{job_id}/reject")
def reject_review(request: Request, job_id: str, payload: ReviewAction):
    return {"status": "rejected", "job_id": job_id, "gate": payload.review_gate}
