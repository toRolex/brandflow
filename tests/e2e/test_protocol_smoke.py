from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.domain_core.models import JobRecord
from packages.file_store.repository import FileStoreRepository


def test_stale_report_rejected_as_orphan(tmp_path: Path) -> None:
    """A report with a mismatched attempt_id is rejected with outcome=orphan."""
    app = create_app(root_dir=tmp_path)
    repo = FileStoreRepository(app.state.root_dir)
    record = JobRecord(
        job_id="j1",
        project_id="p1",
        product="test",
        name="test",
        phase="queued",
        review_status="none",
    )
    repo.save_job("p1", record)

    with TestClient(app) as client:
        # Poll to get a valid task assignment.
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

        # Send a report with a completely bogus attempt_id (stale).
        response = client.post(
            f"/workers/tasks/{poll['task_id']}/report",
            json={
                "worker_id": "worker-win",
                "project_id": poll["project_id"],
                "job_id": poll["job_id"],
                "task_id": poll["task_id"],
                "attempt_id": "attempt-nonexistent",
                "lease_id": poll["lease_id"],
                "status": "succeeded",
                "started_at": "2026-05-18T00:00:00Z",
                "finished_at": "2026-05-18T00:01:00Z",
            },
        )

        assert response.status_code == 200
        assert response.json()["accepted"] is False
        assert response.json()["outcome"] == "orphan"
