from __future__ import annotations

from pathlib import Path
import shutil

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.jobs.helpers import (
    _find_job_project,
    _validate_import_scene_folders,
)
from apps.control_plane.routes.jobs.models import MigrateScenesRequest
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


@router.post("/jobs/{job_id}/migrate-scenes")
def migrate_scenes(request: Request, job_id: str, payload: MigrateScenesRequest):
    """Migrate an import job that lacks valid scene input to use new folders.

    Preserves user-level configuration (manual script, TTS/language settings,
    uploaded audio, cover title, music), clears stale artifacts/runtime files,
    validates the new scene folder selection, and resets the job to ``queued``.
    """
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    record = repo.load_job(project_id, job_id)
    if record.phase != "migration_required":
        raise HTTPException(
            status_code=409, detail="job does not require scene migration"
        )

    validation_error = _validate_import_scene_folders(
        Path(request.app.state.root_dir),
        record.product,
        record.mode,
        payload.scene_folder_ids,
    )
    if validation_error is not None:
        raise HTTPException(status_code=400, detail=validation_error.model_dump())

    # Clear runtime artifacts so the job restarts with clean state.
    job_runtime_dir = (
        Path(request.app.state.root_dir)
        / "workspace"
        / "projects"
        / project_id
        / "runtime"
        / "jobs"
        / job_id
    )
    if job_runtime_dir.exists():
        shutil.rmtree(job_runtime_dir)

    reset_record = record.model_copy(
        update={
            "phase": "queued",
            "review_status": "none",
            "failed_phase": None,
            "scene_folder_ids": payload.scene_folder_ids,
            "artifacts": [],
            "execution": PhaseExecutionState(
                max_attempts=record.execution.max_attempts
            ),
        }
    )
    repo.save_job(project_id, reset_record)
    return {
        "status": "migrated",
        "job_id": job_id,
        "phase": "queued",
        "scene_folder_ids": payload.scene_folder_ids,
    }
