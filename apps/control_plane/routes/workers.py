from fastapi import APIRouter, Request

from apps.control_plane.services.reconcile import choose_report_outcome
from packages.domain_core.models import JobRecord, ArtifactPointer
from packages.domain_core.state import next_phase
from packages.domain_core.worker_protocol import PollRequest, WorkerReport
from packages.file_store.repository import FileStoreRepository

router = APIRouter(prefix="/workers", tags=["workers"])

REVIEW_PHASES = {"script_review", "asset_review", "final_review"}


def _artifact_kind(path: str) -> str:
    """Map artifact file path to a known kind."""
    if path.endswith(".txt") or path.endswith(".json"):
        return "script"
    if path.endswith(".mp3"):
        return "tts_audio"
    if path.endswith(".srt"):
        return "subtitle"
    if path.endswith(".mp4"):
        if "final" in path:
            return "final_video"
        return "source_video"
    return "unknown"


@router.post("/poll")
def poll_worker(payload: PollRequest, request: Request) -> dict[str, object]:
    return request.app.state.dispatcher.poll(payload.worker_id)


@router.get("/tasks/{task_id}/input-bundle")
def download_input_bundle(task_id: str) -> dict[str, object]:
    return {"task_id": task_id, "files": [], "config": {}}


@router.post("/tasks/{task_id}/heartbeat")
def heartbeat(task_id: str, payload: dict[str, object]) -> dict[str, object]:
    return {"accepted": True, "task_id": task_id, "progress": payload}


@router.post("/tasks/{task_id}/artifacts")
def upload_artifacts(task_id: str, payload: dict[str, object]) -> dict[str, object]:
    files = payload.get("files")
    artifact_count = len(files) if isinstance(files, list) else 0
    return {
        "accepted": True,
        "task_id": task_id,
        "artifact_count": artifact_count,
    }


@router.post("/tasks/{task_id}/report")
def report_task(task_id: str, payload: WorkerReport, request: Request) -> dict[str, object]:
    current = request.app.state.dispatcher.current_attempts.get(task_id)
    outcome = choose_report_outcome(current=current, report=payload)
    accepted = outcome == "accept"

    if accepted and payload.status == "succeeded":
        # Advance job phase based on report outcome
        attempt_info = current  # type: ignore[assignment]
        project_id = attempt_info.get("project_id", "")
        job_id = payload.job_id

        if project_id and job_id:
            repo = FileStoreRepository(request.app.state.root_dir)
            try:
                record = repo.load_job(project_id, job_id)
                current_phase = record.phase

                # Build artifacts from report
                artifacts = list(record.artifacts)
                manifest = payload.artifact_manifest
                if manifest and "files" in manifest:
                    for f in manifest["files"]:
                        kind = _artifact_kind(f["relative_path"])
                        artifacts.append(ArtifactPointer(
                            kind=kind,
                            relative_path=f["relative_path"],
                            size_bytes=f.get("size_bytes", 0),
                        ))

                # Advance to next phase
                if current_phase not in REVIEW_PHASES:
                    try:
                        next_p = next_phase(current_phase)
                    except ValueError:
                        next_p = "completed"

                    # If next phase is a review gate, stop there and set pending
                    if next_p in REVIEW_PHASES:
                        record = record.model_copy(update={
                            "phase": next_p,
                            "review_status": "pending",
                            "artifacts": artifacts,
                        })
                    else:
                        record = record.model_copy(update={
                            "phase": next_p,
                            "artifacts": artifacts,
                        })
                else:
                    # Already at a review phase — shouldn't happen via worker
                    record = record.model_copy(update={"artifacts": artifacts})

                repo.save_job(project_id, record)
                repo.append_review_event(project_id, {
                    "job_id": job_id,
                    "event": "worker_report",
                    "from_phase": current_phase,
                    "to_phase": record.phase,
                })
            except Exception:
                pass  # Don't fail the report if state update fails

    return {"accepted": accepted, "outcome": outcome, "task_id": task_id}
