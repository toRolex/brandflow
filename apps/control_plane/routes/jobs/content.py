from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from apps.control_plane.routes.jobs.helpers import _resolve_job_project
from apps.control_plane.routes.jobs.models import UpdateScriptRequest
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


@router.post("/jobs/{job_id}/script")
def update_manual_script(request: Request, job_id: str, payload: UpdateScriptRequest):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _resolve_job_project(repo, job_id)

    record = repo.load_job(project_id, job_id)
    repo.save_job(
        project_id, record.model_copy(update={"manual_script": payload.manual_script})
    )
    return {
        "status": "updated",
        "job_id": job_id,
        "manual_script": payload.manual_script,
    }


@router.post("/jobs/{job_id}/audio")
async def upload_job_audio(request: Request, job_id: str, file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    repo = FileStoreRepository(request.app.state.root_dir)
    layout = repo.layout
    project_id = _resolve_job_project(repo, job_id)
    record = repo.load_job(project_id, job_id)
    if record.phase != "draft":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_AUDIO_UPLOAD_NOT_ALLOWED",
                "message": "audio can only be uploaded while the job is a draft",
                "retryable": False,
            },
        )

    safe_name = f"{job_id}_{Path(file.filename).name}"
    dest = layout.audio_path(project_id, safe_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    dest.write_bytes(content)

    relative_path = dest.relative_to(layout.root).as_posix()
    repo.save_job(
        project_id, record.model_copy(update={"uploaded_audio_path": relative_path})
    )

    return {
        "status": "uploaded",
        "job_id": job_id,
        "audio_path": relative_path,
        "size_bytes": len(content),
    }
