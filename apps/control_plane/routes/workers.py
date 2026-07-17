from fastapi import APIRouter, Request

from apps.control_plane.services.reconcile import choose_report_outcome
from packages.domain_core.models import ExecutionFailure
from packages.domain_core.worker_protocol import PollRequest, WorkerReport
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import JobTickService

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
def report_task(
    task_id: str, payload: WorkerReport, request: Request
) -> dict[str, object]:
    current = request.app.state.dispatcher.current_attempts.get(task_id)
    outcome = choose_report_outcome(current=current, report=payload)
    accepted = outcome == "accept"

    if accepted:
        attempt_info = current or {}
        project_id = attempt_info.get("project_id", "")
        job_id = payload.job_id
        handler_phase = attempt_info.get("handler_phase")

        if project_id and job_id:
            try:
                repo = FileStoreRepository(request.app.state.root_dir)
                orchestrator = getattr(request.app.state, "orchestrator", None)
                if orchestrator is None:
                    raise RuntimeError(
                        "orchestrator not available on app.state — "
                        "cannot advance job after worker report"
                    )

                tick_svc = JobTickService(orchestrator=orchestrator, repo=repo)
                manifest_files = list(
                    (payload.artifact_manifest or {}).get("files", [])
                )

                if payload.status == "succeeded":
                    _ = tick_svc.advance_after_report(
                        project_id,
                        job_id,
                        manifest_files,
                        handler_phase=handler_phase,
                    )
                elif payload.status == "failed":
                    # Wire the worker's error into the shared failure-transition
                    # logic so attempt counting and retry-exhaustion are
                    # consistent with the auto-tick path (#171).
                    raw_error = payload.error or {}
                    error = ExecutionFailure(
                        code=raw_error.get("code", "WORKER_REPORTED_FAILURE"),
                        message=raw_error.get("message", ""),
                        retryable=raw_error.get("retryable", True),
                    )
                    _ = tick_svc.advance_after_report(
                        project_id,
                        job_id,
                        manifest_files,
                        handler_phase=handler_phase,
                        error=error,
                    )
            except Exception:
                import traceback

                traceback.print_exc()

    return {"accepted": accepted, "outcome": outcome, "task_id": task_id}
