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
    with TestClient(create_app()) as client:
        response = client.get("/")
        assert response.status_code == 200


def test_poll_returns_idle_when_queue_is_empty(tmp_path: Path) -> None:
    with TestClient(create_app(root_dir=tmp_path)) as client:
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
    with TestClient(app) as client:
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
    with TestClient(app) as client:
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
    with TestClient(app) as client:
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
    with TestClient(app) as client:
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


class TestWorkerReportState:
    """State assertions: worker success/failure reports correctly advance job phase."""

    def _poll_and_report(
        self,
        app,
        *,
        project_id: str = "p1",
        job_id: str = "j1",
        status: str = "succeeded",
        manifest_files: list[dict[str, object]] | None = None,
        error: dict[str, object] | None = None,
    ) -> dict[str, object]:
        _save_test_job(app, project_id, job_id)
        with TestClient(app) as client:
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
            return client.post(
                f"/workers/tasks/{poll['task_id']}/report",
                json={
                    "worker_id": "worker-win",
                    "project_id": poll["project_id"],
                    "job_id": poll["job_id"],
                    "task_id": poll["task_id"],
                    "attempt_id": poll["attempt_id"],
                    "lease_id": poll["lease_id"],
                    "status": status,
                    "started_at": "2026-05-18T00:00:00Z",
                    "finished_at": "2026-05-18T00:01:00Z",
                    "artifact_manifest": {"files": manifest_files or []},
                    "metrics": {},
                    "logs_summary": "ok",
                    "error": error or {},
                },
            ).json()

    def test_success_report_advances_phase(self, tmp_path: Path) -> None:
        app = create_app(root_dir=tmp_path)
        self._poll_and_report(
            app,
            manifest_files=[{"relative_path": "script.txt", "size_bytes": 512}],
        )
        repo = FileStoreRepository(tmp_path)
        saved = repo.load_job("p1", "j1")
        # queued dispatches script_generating; success → script_review
        assert saved.phase == "script_review"
        assert saved.execution.status == "succeeded"
        assert saved.execution.current_attempt == 1

    def test_success_report_merges_artifacts(self, tmp_path: Path) -> None:
        app = create_app(root_dir=tmp_path)
        self._poll_and_report(
            app,
            manifest_files=[
                {"relative_path": "script.txt", "size_bytes": 512},
                {"relative_path": "audio.mp3", "size_bytes": 2048},
            ],
        )
        repo = FileStoreRepository(tmp_path)
        saved = repo.load_job("p1", "j1")
        artifact_kinds = {a.kind for a in saved.artifacts}
        assert "script" in artifact_kinds
        assert "tts_audio" in artifact_kinds

    def test_retryable_failure_report_enters_retrying(self, tmp_path: Path) -> None:
        app = create_app(root_dir=tmp_path)
        self._poll_and_report(
            app,
            status="failed",
            manifest_files=[{"relative_path": "audio.mp3", "size_bytes": 1024}],
            error={
                "code": "MEDIA_PROCESSING_TIMEOUT",
                "message": "Media processing timed out.",
                "retryable": True,
            },
        )
        repo = FileStoreRepository(tmp_path)
        saved = repo.load_job("p1", "j1")
        assert saved.execution.status == "retrying"
        assert saved.execution.current_attempt == 1
        assert saved.execution.error is not None
        assert saved.execution.error.retryable is True

    def test_non_retryable_failure_report_goes_terminal(self, tmp_path: Path) -> None:
        app = create_app(root_dir=tmp_path)
        self._poll_and_report(
            app,
            status="failed",
            manifest_files=[],
            error={
                "code": "VIDEO_SOURCE_MISSING",
                "message": "No usable video source available.",
                "retryable": False,
            },
        )
        repo = FileStoreRepository(tmp_path)
        saved = repo.load_job("p1", "j1")
        assert saved.phase == "failed"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 1
