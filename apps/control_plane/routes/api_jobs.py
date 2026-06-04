from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from packages.domain_core.models import JobRecord
from packages.domain_core.state import next_phase
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


class CreateJobRequest(BaseModel):
    product: str
    platforms: list[str]
    asset: str | None = None
    manual_script: str = ""
    uploaded_audio_path: str = ""


class ReviewAction(BaseModel):
    review_gate: str


@router.post("/api/projects/{project_id}/jobs")
def create_job(request: Request, project_id: str, payload: CreateJobRequest):
    job_id = f"job_{payload.product}_{uuid4().hex[:8]}"
    dispatcher = request.app.state.dispatcher
    dispatcher.enqueue_demo_job(
        project_id,
        job_id,
        manual_script=payload.manual_script,
        uploaded_audio_path=payload.uploaded_audio_path,
    )
    repo = FileStoreRepository(request.app.state.root_dir)
    repo.save_job(project_id, JobRecord(
        job_id=job_id,
        project_id=project_id,
        product=payload.product,
        phase="queued",
        review_status="none",
        manual_script=payload.manual_script,
        uploaded_audio_path=payload.uploaded_audio_path,
    ))
    return {
        "job_id": job_id,
        "project_id": project_id,
        "product": payload.product,
        "platforms": payload.platforms,
        "phase": "queued",
        "review_status": "none",
        "artifacts": [],
        "manual_script": payload.manual_script,
        "uploaded_audio_path": payload.uploaded_audio_path,
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


class UpdateScriptRequest(BaseModel):
    manual_script: str


@router.post("/api/jobs/{job_id}/script")
def update_manual_script(request: Request, job_id: str, payload: UpdateScriptRequest):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"manual_script": payload.manual_script}))
    return {"status": "updated", "job_id": job_id, "manual_script": payload.manual_script}


@router.post("/api/jobs/{job_id}/audio")
async def upload_job_audio(request: Request, job_id: str, file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    
    root_dir: Path = request.app.state.root_dir
    audio_dir = root_dir / "workspace" / "projects" / project_id / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    
    safe_name = f"{job_id}_{Path(file.filename).name}"
    dest = audio_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)
    
    relative_path = f"workspace/projects/{project_id}/audio/{safe_name}"
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"uploaded_audio_path": relative_path}))
    
    return {
        "status": "uploaded",
        "job_id": job_id,
        "audio_path": relative_path,
        "size_bytes": len(content),
    }


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
