from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.jobs.helpers import (
    _find_job_project,
    _make_job_response,
    _resolve_product_defaults,
    _validate_import_scene_folders,
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


@router.post("/projects/{project_id}/jobs")
def create_job(request: Request, project_id: str, payload: CreateJobRequest):
    product, brand = _resolve_product_defaults(
        payload.product, payload.brand, request.app.state.root_dir
    )
    if not product.strip():
        raise HTTPException(status_code=400, detail="product is required")
    validation_error = _validate_import_scene_folders(
        Path(request.app.state.root_dir),
        product,
        payload.mode,
        payload.scene_folder_ids,
    )
    if validation_error is not None:
        raise HTTPException(status_code=400, detail=validation_error.model_dump())

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
        scene_folder_ids=payload.scene_folder_ids,
    )
    repo.save_job(project_id, record)

    # 计算 display_index：当前已有 job 数 + 1
    existing_jobs = repo.list_jobs(project_id)
    display_index = f"{len(existing_jobs):03d}"

    return _make_job_response(record, display_index, payload.platforms)


@router.post("/projects/{project_id}/jobs/batch")
def create_jobs_batch(request: Request, project_id: str, payload: BatchCreateRequest):
    product, brand = _resolve_product_defaults(
        payload.product, payload.brand, request.app.state.root_dir
    )
    if not product.strip():
        raise HTTPException(status_code=400, detail="product is required")
    root_dir_path = Path(request.app.state.root_dir)

    # Phase 1: Validate all items before persisting any.
    validation_errors: list[dict[str, object]] = []
    for i, item in enumerate(payload.jobs):
        validation_error = _validate_import_scene_folders(
            root_dir_path,
            product,
            item.mode,
            item.scene_folder_ids,
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
            name=item.name or product,
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
            scene_folder_ids=item.scene_folder_ids,
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


@router.post("/jobs/{job_id}/pause")
def pause_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"phase": "paused"}))
    return {"status": "paused", "job_id": job_id}


@router.delete("/jobs/{job_id}")
def delete_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
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
