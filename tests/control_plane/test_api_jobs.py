from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _make_client(tmp_path: Path):
    return TestClient(create_app(tmp_path))


def test_delete_job_success(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    # Create a job first
    client.post("/api/projects/prj_001/jobs", json={
        "product": "test", "platforms": ["douyin"],
    })
    # Find the job_id from the response
    jobs = client.get("/api/projects/prj_001").json().get("jobs", [])
    assert len(jobs) == 1
    job_id = jobs[0]["job_id"]

    resp = client.delete(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "job_id": job_id}

    # Verify job is gone
    resp2 = client.get(f"/api/jobs/{job_id}")
    assert resp2.status_code == 404


def test_delete_job_not_found(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    resp = client.delete("/api/jobs/nonexistent_job")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "job not found"}
