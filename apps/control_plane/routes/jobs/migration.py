from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.jobs.helpers import (
    _find_job_project,
)
from packages.domain_core.models import PhaseExecutionState
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


@router.post("/jobs/{job_id}/retry")
def retry_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    if record.phase != "failed":
        raise HTTPException(status_code=409, detail="job has no failed phase to retry")
    if record.failed_phase is None:
        # Legacy failed jobs (no structured failed_phase yet, e.g. generate/
        # worker paths not migrated to the execution contract): keep the old
        # reset-to-queued retry behaviour instead of rejecting them.
        repo.save_job(
            project_id,
            record.model_copy(
                update={
                    "phase": "queued",
                    "review_status": "none",
                    "execution": PhaseExecutionState(
                        max_attempts=record.execution.max_attempts
                    ),
                }
            ),
        )
        return {"status": "queued_for_retry", "job_id": job_id}

    from packages.pipeline_services.phase_orchestrator import PhaseContext

    project_dir = request.app.state.root_dir / "workspace" / "projects" / project_id
    scene_config = request.app.state.config_reader.get_scene_config(
        product_id=record.product
    )
    configured_paths = [
        entry.get("path", "")
        for entry in scene_config.get("folders", [])
        if entry.get("path")
    ]
    scene_folder_paths = (
        record.scene_folder_ids
        if record.mode == "import" and record.scene_folder_ids
        else configured_paths
    )
    ctx = PhaseContext(
        job_id=record.job_id,
        project_dir=project_dir,
        root_dir=request.app.state.root_dir,
        product=record.product,
        brand=record.brand,
        options={
            "manual_script": record.manual_script,
            "uploaded_audio_path": record.uploaded_audio_path,
            "language": record.language,
            "mode": record.mode,
        },
        scene_folder_paths=scene_folder_paths,
        transition_duration_ms=scene_config.get("transition_duration_ms", 500),
        scene_config=scene_config,
    )
    from apps.control_plane.app import _get_orchestrator

    validation_error = _get_orchestrator(request.app).validate_phase_input(
        record.failed_phase, ctx
    )
    if validation_error is not None:
        raise HTTPException(status_code=409, detail=validation_error.model_dump())

    repo.save_job(
        project_id,
        record.model_copy(
            update={
                "phase": record.failed_phase,
                "failed_phase": None,
                "review_status": "none",
                "execution": PhaseExecutionState(
                    max_attempts=record.execution.max_attempts
                ),
            }
        ),
    )
    return {"status": "phase_queued_for_retry", "job_id": job_id}
