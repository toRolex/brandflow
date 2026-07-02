from fastapi import APIRouter, Request

from apps.control_plane.services.reconcile import choose_report_outcome
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

    if accepted and payload.status == "succeeded":
        attempt_info = current  # type: ignore[assignment]
        project_id = attempt_info.get("project_id", "")
        job_id = payload.job_id

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
                manifest_files = (payload.artifact_manifest or {}).get("files", [])
                _ = tick_svc.advance_after_report(
                    project_id, job_id, list(manifest_files)
                )
            except Exception:
                pass

    return {"accepted": accepted, "outcome": outcome, "task_id": task_id}
