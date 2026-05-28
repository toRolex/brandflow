from __future__ import annotations

import json
from pathlib import Path

from packages.domain_core.models import JobRecord
from packages.file_store.repository import FileStoreRepository


def test_create_project_layout(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)

    project_root = repo.create_project("project-001")

    expected_dirs = [
        project_root / "control" / "jobs",
        project_root / "control" / "batches",
        project_root / "reviews",
        project_root / "reports",
        project_root / "runtime" / "jobs",
        project_root / "runtime" / "source_assets",
        project_root / "runtime" / "schedule" / "exports",
        project_root / "logs",
    ]

    assert project_root == tmp_path / "workspace" / "projects" / "project-001"
    for path in expected_dirs:
        assert path.exists()
        assert path.is_dir()


def test_save_and_load_job_record(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")
    record = JobRecord(job_id="job-1", phase="queued", review_status="none")

    repo.save_job("project-001", record)

    loaded = repo.load_job("project-001", "job-1")
    assert loaded == record
    raw = json.loads(
        (
            tmp_path
            / "workspace"
            / "projects"
            / "project-001"
            / "control"
            / "jobs"
            / "job-1.json"
        ).read_text(encoding="utf-8")
    )
    assert raw["job_id"] == "job-1"


def test_append_review_event(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")

    repo.append_review_event("project-001", {"job_id": "job-1", "action": "approve"})
    repo.append_review_event("project-001", {"job_id": "job-1", "action": "reject"})

    lines = (
        tmp_path
        / "workspace"
        / "projects"
        / "project-001"
        / "reviews"
        / "review_events.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["action"] for line in lines] == ["approve", "reject"]


def test_delete_job_removes_json_file_and_runtime_dir(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("prj_001")
    record = JobRecord(job_id="job_test_001", project_id="prj_001", product="test", phase="queued", review_status="none")
    repo.save_job("prj_001", record)
    json_path = tmp_path / "workspace" / "projects" / "prj_001" / "control" / "jobs" / "job_test_001.json"
    assert json_path.exists()

    # Create a runtime artifacts directory with some files
    runtime_dir = tmp_path / "workspace" / "projects" / "prj_001" / "runtime" / "jobs" / "job_test_001"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "script.txt").write_text("test script")
    (runtime_dir / "tts_audio.mp3").write_bytes(b"fake audio")
    assert runtime_dir.exists()

    result = repo.delete_job("prj_001", "job_test_001")
    assert result is True
    assert not json_path.exists()
    assert not runtime_dir.exists()


def test_delete_job_not_found_returns_false(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("prj_001")
    result = repo.delete_job("prj_001", "nonexistent")
    assert result is False
