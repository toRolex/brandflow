from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.domain_core.models import JobRecord
from packages.file_store.repository import FileStoreRepository


def _save_test_job(app, project_id: str, job_id: str, **overrides: object) -> None:
    repo = FileStoreRepository(app.state.root_dir)
    record = JobRecord(
        job_id=job_id,
        project_id=project_id,
        product="test",
        name="test",
        phase="queued",
        review_status="none",
        **overrides,
    )
    repo.save_job(project_id, record)


@pytest.mark.e2e
def test_root_serves_frontend() -> None:
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200


def test_poll_returns_idle_when_queue_is_empty(tmp_path: Path) -> None:
    client = TestClient(create_app(root_dir=tmp_path))
    response = client.post(
        "/workers/poll",
        json={
            "worker_id": "worker-mac",
            "worker_version": "0.1.0",
            "capabilities": ["mac-local"],
            "current_tasks": [],
            "free_slots": 1,
        },
    )
    assert response.status_code == 200
    assert response.json()["command"] == "idle"


def test_poll_returns_run_task_when_job_is_queued(tmp_path: Path) -> None:
    app = create_app(root_dir=tmp_path)
    _save_test_job(app, project_id="p1", job_id="j1")
    client = TestClient(app)
    response = client.post(
        "/workers/poll",
        json={
            "worker_id": "worker-win",
            "worker_version": "0.1.0",
            "capabilities": ["windows-prod"],
            "current_tasks": [],
            "free_slots": 1,
        },
    )
    payload = response.json()
    assert payload["command"] == "run_task"
    assert payload["project_id"] == "p1"
    assert payload["handler_phase"] == "script_generating"
    assert payload["attempt_id"]


def test_heartbeat_endpoint_accepts_progress_for_current_task(
    tmp_path: Path,
) -> None:
    app = create_app(root_dir=tmp_path)
    _save_test_job(app, project_id="p1", job_id="j1")
    client = TestClient(app)
    poll = client.post(
        "/workers/poll",
        json={
            "worker_id": "worker-win",
            "worker_version": "0.1.0",
            "capabilities": ["windows-prod"],
            "current_tasks": [],
            "free_slots": 1,
        },
    ).json()
    response = client.post(
        f"/workers/tasks/{poll['task_id']}/heartbeat",
        json={"phase": "script_generating", "percent": 25},
    )
    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "task_id": poll["task_id"],
        "progress": {"phase": "script_generating", "percent": 25},
    }


def test_artifacts_endpoint_accepts_current_task_outputs(tmp_path: Path) -> None:
    app = create_app(root_dir=tmp_path)
    _save_test_job(app, project_id="p1", job_id="j1")
    client = TestClient(app)
    poll = client.post(
        "/workers/poll",
        json={
            "worker_id": "worker-win",
            "worker_version": "0.1.0",
            "capabilities": ["windows-prod"],
            "current_tasks": [],
            "free_slots": 1,
        },
    ).json()
    response = client.post(
        f"/workers/tasks/{poll['task_id']}/artifacts",
        json={
            "files": [
                {"kind": "script", "path": "runtime/jobs/j1/script.json"},
                {"kind": "final_video", "path": "runtime/jobs/j1/final/out.mp4"},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "task_id": poll["task_id"],
        "artifact_count": 2,
    }


def test_report_endpoint_accepts_current_attempt(tmp_path: Path) -> None:
    app = create_app(root_dir=tmp_path)
    _save_test_job(app, project_id="p1", job_id="j1")
    client = TestClient(app)
    poll = client.post(
        "/workers/poll",
        json={
            "worker_id": "worker-win",
            "worker_version": "0.1.0",
            "capabilities": ["windows-prod"],
            "current_tasks": [],
            "free_slots": 1,
        },
    ).json()
    response = client.post(
        f"/workers/tasks/{poll['task_id']}/report",
        json={
            "worker_id": "worker-win",
            "project_id": poll["project_id"],
            "job_id": poll["job_id"],
            "task_id": poll["task_id"],
            "attempt_id": poll["attempt_id"],
            "lease_id": poll["lease_id"],
            "status": "succeeded",
            "started_at": "2026-05-18T00:00:00Z",
            "finished_at": "2026-05-18T00:01:00Z",
            "artifact_manifest": {"final": "runtime/jobs/j1/final/out.mp4"},
            "metrics": {},
            "logs_summary": "ok",
            "error": {},
        },
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True
