from fastapi import APIRouter, Request

from apps.control_plane.services.reconcile import choose_report_outcome
from packages.domain_core.worker_protocol import PollRequest, WorkerReport

router = APIRouter(prefix="/workers", tags=["workers"])


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
    return {"accepted": accepted, "outcome": outcome, "task_id": task_id}
