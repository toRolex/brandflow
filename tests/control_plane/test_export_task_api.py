"""HTTP workflow tests for the background export task API (#180).

Covers the control-plane seam: create returns a task id (not a blocking ZIP),
status polling exposes queued/running/ready/failed/stale + progress, download
gates on ready, and rerender/restart recovery flows.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.file_store.repository import FileStoreRepository


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEV_AUTO_TICK", "0")
    monkeypatch.setenv("EXPORT_SYNC", "1")
    app = create_app(root_dir=tmp_path)
    return TestClient(app)


def _setup_completed_job(client: TestClient, project_id: str, job_id: str) -> Path:
    """Create a completed job with a final_timeline.json fingerprint on disk."""
    root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
    repo = FileStoreRepository(root)
    repo.create_project(project_id, "test")
    job_dir = root / "workspace" / "projects" / project_id / "runtime" / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:d=0.4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.4",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            str(job_dir / "final.mp4"),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=0.4",
            "-c:a",
            "libmp3lame",
            str(job_dir / "audio.mp3"),
        ],
        check=True,
        capture_output=True,
    )
    (job_dir / "final_timeline.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "duration_ms": 400,
                "fingerprint": "fp-abc",
                "segments": [
                    {
                        "kind": "montage",
                        "start_ms": 0,
                        "end_ms": 400,
                        "sentence_index": 0,
                        "text": "test",
                    }
                ],
            }
        )
    )
    record = (
        repo.load_job(project_id, job_id)
        if (
            repo.root
            / "workspace"
            / "projects"
            / project_id
            / "control"
            / "jobs"
            / f"{job_id}.json"
        ).exists()
        else None
    )
    if record is None:
        from packages.domain_core.models import JobRecord

        record = JobRecord(
            job_id=job_id,
            project_id=project_id,
            product="p",
            brand="b",
            platforms=["douyin"],
            mode="generate",
            phase="completed",
            review_status="approved",
        )
    else:
        record = record.model_copy(update={"phase": "completed"})
    repo.save_job(project_id, record)
    return job_dir


class TestCreateExport:
    def test_create_returns_task_id_not_blocking_zip(self, client: TestClient) -> None:
        _setup_completed_job(client, "proj-1", "job-1")
        resp = client.post("/api/jobs/job-1/export")
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["task_id"]
        assert body["status"] in ("queued", "running", "ready")
        # Must NOT be a ZIP download.
        assert resp.headers["content-type"] != "application/zip"

    def test_create_on_unfinished_job_rejected(self, client: TestClient) -> None:
        root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
        repo = FileStoreRepository(root)
        repo.create_project("proj-2", "t")
        from packages.domain_core.models import JobRecord

        repo.save_job(
            "proj-2",
            JobRecord(
                job_id="job-2",
                project_id="proj-2",
                product="p",
                brand="b",
                platforms=["douyin"],
                mode="generate",
                phase="script_review",
                review_status="pending",
            ),
        )
        resp = client.post("/api/jobs/job-2/export")
        assert resp.status_code == 400

    def test_missing_final_timeline_requires_rerender(self, client: TestClient) -> None:
        """Legacy job without a Final Timeline gets a clear rerender-required error."""
        root = Path(client.app.state.root_dir)  # type: ignore[union-attr]
        repo = FileStoreRepository(root)
        repo.create_project("proj-3", "t")
        job_dir = (
            root / "workspace" / "projects" / "proj-3" / "runtime" / "jobs" / "job-3"
        )
        job_dir.mkdir(parents=True, exist_ok=True)
        from packages.domain_core.models import JobRecord

        repo.save_job(
            "proj-3",
            JobRecord(
                job_id="job-3",
                project_id="proj-3",
                product="p",
                brand="b",
                platforms=["douyin"],
                mode="generate",
                phase="completed",
                review_status="approved",
            ),
        )
        resp = client.post("/api/jobs/job-3/export")
        assert resp.status_code == 409
        assert "rerender" in resp.json()["detail"].lower()


class TestStatusAndDownload:
    def test_status_reports_state_and_progress(self, client: TestClient) -> None:
        _setup_completed_job(client, "proj-1", "job-1")
        client.post("/api/jobs/job-1/export")
        resp = client.get("/api/jobs/job-1/export/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("queued", "running", "ready", "failed", "stale")
        assert "progress" in body

    def test_ready_task_downloads_zip(self, client: TestClient) -> None:
        _setup_completed_job(client, "proj-1", "job-1")
        client.post("/api/jobs/job-1/export")
        # Synchronous executor in tests completes inline.
        status = client.get("/api/jobs/job-1/export/status").json()
        assert status["status"] == "ready"

        resp = client.get("/api/jobs/job-1/export/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

    def test_download_before_ready_rejected(self, client: TestClient) -> None:
        _setup_completed_job(client, "proj-1", "job-1")
        # No export created yet → nothing to download.
        resp = client.get("/api/jobs/job-1/export/download")
        assert resp.status_code == 409


class TestRerenderStale:
    def test_rerender_makes_export_stale_and_undownloadable(
        self, client: TestClient
    ) -> None:
        _setup_completed_job(client, "proj-1", "job-1")
        client.post("/api/jobs/job-1/export")
        assert client.get("/api/jobs/job-1/export/status").json()["status"] == "ready"

        # Rerender → new fingerprint on disk → old export must go stale.
        job_dir = (
            Path(client.app.state.root_dir)  # type: ignore[union-attr]
            / "workspace"
            / "projects"
            / "proj-1"
            / "runtime"
            / "jobs"
            / "job-1"
        )
        (job_dir / "final_timeline.json").write_text(
            json.dumps({"version": "1.0", "fingerprint": "fp-NEW", "segments": []})
        )
        # Trigger stale marking (the rerender path calls this endpoint).
        client.post("/api/jobs/job-1/export/invalidate")

        status = client.get("/api/jobs/job-1/export/status").json()
        assert status["status"] == "stale"
        resp = client.get("/api/jobs/job-1/export/download")
        assert resp.status_code == 409
