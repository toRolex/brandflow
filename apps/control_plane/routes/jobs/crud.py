from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.jobs.helpers import (
    _find_job_project,
    _make_job_response,
    _resolve_product_from_config,
    _validate_tts_model_voice,
)
from apps.control_plane.routes.jobs.models import (
    BatchCreateRequest,
    CreateJobRequest,
    RenameJobRequest,
    _cover_title_from_request,
)
from packages.domain_core.models import JobRecord
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


_DELETE_ALLOWED_PHASES = frozenset({"paused", "failed", "cancelled", "completed"})
_ACTIVE_PHASES = frozenset(
    {
        "queued",
        "script_generating",
        "script_review",
        "scene_assembling",
        "tts_generating",
        "tts_review",
        "subtitle_generating",
        "montage_assembling",
        "asset_retrieving",
        "asset_review",
        "video_rendering",
        "final_rendering",
        "final_review",
    }
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@router.post("/projects/{project_id}/jobs")
def create_job(request: Request, project_id: str, payload: CreateJobRequest):
    product, brand = _resolve_product_from_config(request.app.state.root_dir)
    if not product.strip():
        raise HTTPException(status_code=400, detail="product is required — set default_name in product config")

    tts_validation_error = _validate_tts_model_voice(
        payload.tts_model,
        payload.tts_voice,
        product,
        request.app.state.config_reader,
    )
    if tts_validation_error is not None:
        raise HTTPException(status_code=422, detail=tts_validation_error.model_dump())

    job_id = f"job_{product}_{uuid4().hex[:8]}"
    repo = FileStoreRepository(request.app.state.root_dir)
    record = JobRecord(
        job_id=job_id,
        project_id=project_id,
        product=product,
        brand=brand,
        name=payload.name or product,
        mode=payload.mode,
        phase="queued",
        review_status="none",
        manual_script=payload.manual_script,
        uploaded_audio_path=payload.uploaded_audio_path,
        audio_source=payload.audio_source,
        skip_subtitle=payload.skip_subtitle,
        auto_approve=payload.auto_approve,
        language=payload.language,
        cover_title=_cover_title_from_request(payload.cover_title),
        music_track_path=payload.music_track_path,
        music_volume=payload.music_volume,
        tts_model=payload.tts_model,
        tts_voice=payload.tts_voice,
    )
    repo.save_job(project_id, record)

    # 计算 display_index：当前已有 job 数 + 1
    existing_jobs = repo.list_jobs(project_id)
    display_index = f"{len(existing_jobs):03d}"

    return _make_job_response(record, display_index, payload.platforms)


@router.post("/projects/{project_id}/jobs/batch")
def create_jobs_batch(request: Request, project_id: str, payload: BatchCreateRequest):
    product, brand = _resolve_product_from_config(request.app.state.root_dir)
    if not product.strip():
        raise HTTPException(status_code=400, detail="product is required — set default_name in product config")

    # Phase 1: Validate all items before persisting any.
    validation_errors: list[dict[str, object]] = []
    for i, item in enumerate(payload.jobs):
        validation_error = _validate_tts_model_voice(
            item.tts_model,
            item.tts_voice,
            product,
            request.app.state.config_reader,
        )
        if validation_error is not None:
            validation_errors.append(
                {
                    "index": i,
                    "item_name": item.name or f"#{i + 1}",
                    "error": validation_error.model_dump(),
                }
            )

    if validation_errors:
        first: dict[str, Any] = validation_errors[0]
        first_error: dict[str, Any] = first["error"]
        index: int = int(first["index"])
        item_name: str = str(first["item_name"])
        raise HTTPException(
            status_code=400,
            detail={
                "code": "BATCH_VALIDATION_FAILED",
                "message": (
                    f"批量创建验证失败：第 {index + 1} 项「{item_name}」"
                    f" — {first_error['message']}"
                ),
                "retryable": False,
                "errors": validation_errors,
            },
        )

    # Phase 2: All items passed validation — persist them.
    repo = FileStoreRepository(request.app.state.root_dir)
    existing_count = len(repo.list_jobs(project_id))

    results: list[dict] = []
    for i, item in enumerate(payload.jobs):
        job_id = f"job_{product}_{uuid4().hex[:8]}"
        cover_title = _cover_title_from_request(item.cover_title)
        record = JobRecord(
            job_id=job_id,
            project_id=project_id,
            product=product,
            brand=brand,
            name=item.name or f"{product} #{i + 1:03d}",
            mode=item.mode,
            phase="queued",
            review_status="none",
            manual_script=item.manual_script,
            uploaded_audio_path="",
            audio_source=item.audio_source,
            skip_subtitle=item.skip_subtitle,
            auto_approve=payload.auto_approve,
            language=item.language,
            cover_title=cover_title,
            music_track_path=item.music_track_path,
            music_volume=item.music_volume,
            tts_model=item.tts_model,
            tts_voice=item.tts_voice,
        )
        repo.save_job(project_id, record)
        display_index = f"{existing_count + i + 1:03d}"
        results.append(_make_job_response(record, display_index, payload.platforms))

    return {
        "product": product,
        "platforms": payload.platforms,
        "mode": payload.mode,
        "auto_approve": payload.auto_approve,
        "count": len(results),
        "results": results,
    }


@router.get("/jobs/{job_id}")
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


@router.post("/jobs/{job_id}/pause", status_code=202)
def pause_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    if record.phase not in _ACTIVE_PHASES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_PAUSE_NOT_ALLOWED",
                "message": f"cannot pause a job in {record.phase}",
                "retryable": False,
            },
        )
    if not record.pause_requested:
        repo.save_job(
            project_id,
            record.model_copy(
                update={"pause_requested": True, "paused_at": _utc_now()}
            ),
        )
    return {"status": "pause_requested", "job_id": job_id}


@router.post("/jobs/{job_id}/resume")
def resume_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    if record.phase != "paused" or record.paused_from_phase is None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_RESUME_NOT_ALLOWED",
                "message": "job is not paused at a resumable phase",
                "retryable": False,
            },
        )
    resumed = record.model_copy(
        update={
            "phase": record.paused_from_phase,
            "pause_requested": False,
            "paused_from_phase": None,
            "paused_at": "",
        }
    )
    repo.save_job(project_id, resumed)
    return {"status": "resumed", "job_id": job_id, "phase": resumed.phase}


@router.post("/jobs/{job_id}/cancel", status_code=202)
def cancel_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    if record.phase == "cancelled":
        return {"status": "cancelled", "job_id": job_id}
    if record.phase == "paused":
        repo.save_job(
            project_id,
            record.model_copy(
                update={
                    "phase": "cancelled",
                    "pause_requested": False,
                    "cancellation_requested": False,
                }
            ),
        )
        return {"status": "cancelled", "job_id": job_id}
    if record.phase not in _ACTIVE_PHASES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_CANCEL_NOT_ALLOWED",
                "message": f"cannot cancel a job in {record.phase}",
                "retryable": False,
            },
        )
    if not record.cancellation_requested:
        repo.save_job(
            project_id,
            record.model_copy(update={"cancellation_requested": True}),
        )
    return {"status": "cancellation_requested", "job_id": job_id}


@router.delete("/jobs/{job_id}")
def delete_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    if record.phase not in _DELETE_ALLOWED_PHASES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "JOB_DELETE_NOT_ALLOWED",
                "message": f"cancel the active job before deleting it ({record.phase})",
                "retryable": False,
            },
        )
    repo.delete_job(project_id, job_id)
    return {"status": "deleted", "job_id": job_id}


@router.put("/jobs/{job_id}/rename")
def rename_job(request: Request, job_id: str, payload: RenameJobRequest):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"name": payload.name}))
    return {"job_id": job_id, "name": payload.name}
