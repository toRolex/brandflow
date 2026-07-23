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
    assert raw["skip_subtitle"] is False
    assert raw["auto_approve"] is False


def test_save_and_load_job_record_preserves_true_flags(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")
    record = JobRecord(
        job_id="job-1",
        phase="queued",
        review_status="none",
        skip_subtitle=True,
        auto_approve=True,
    )

    repo.save_job("project-001", record)

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
    assert raw["skip_subtitle"] is True
    assert raw["auto_approve"] is True
    assert repo.load_job("project-001", "job-1") == record


def test_append_review_event(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")

    repo.append_review_event("project-001", {"job_id": "job-1", "action": "approve"})
    repo.append_review_event("project-001", {"job_id": "job-1", "action": "reject"})

    lines = (
        (
            tmp_path
            / "workspace"
            / "projects"
            / "project-001"
            / "reviews"
            / "review_events.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
    )
    assert [json.loads(line)["action"] for line in lines] == ["approve", "reject"]


def test_delete_job_removes_json_file_and_runtime_dir(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("prj_001")
    record = JobRecord(
        job_id="job_test_001",
        project_id="prj_001",
        product="test",
        phase="queued",
        review_status="none",
    )
    repo.save_job("prj_001", record)
    json_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "control"
        / "jobs"
        / "job_test_001.json"
    )
    assert json_path.exists()

    # Create a runtime artifacts directory with some files
    runtime_dir = (
        tmp_path
        / "workspace"
        / "projects"
        / "prj_001"
        / "runtime"
        / "jobs"
        / "job_test_001"
    )
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


# ——— list_jobs 排序与 display_index ———


def test_list_jobs_empty_project_returns_empty_list(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")

    result = repo.list_jobs("project-001")

    assert result == []


def test_list_jobs_includes_asset_review_unresolved_count(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")
    repo.save_job(
        "project-001",
        JobRecord(job_id="job-assets", phase="asset_review", review_status="pending"),
    )
    clips_path = (
        tmp_path
        / "workspace"
        / "projects"
        / "project-001"
        / "runtime"
        / "jobs"
        / "job-assets"
        / "selected_clips.json"
    )
    clips_path.parent.mkdir(parents=True)
    clips_path.write_text(
        json.dumps(
            [{"visual_type": "unresolved"}, {"visual_type": "blank"}, {"visual_type": "unresolved"}]
        ),
        encoding="utf-8",
    )

    result = repo.list_jobs("project-001")

    assert result[0]["asset_review_unresolved_count"] == 2


def test_list_jobs_returns_sorted_by_mtime_with_display_index(tmp_path: Path) -> None:
    """按 mtime 升序返回，并分配 001/002 三位数 display_index。"""
    import time

    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")

    # 先创建 job_b，再创建 job_a，让 job_a 的 mtime 更大
    record_b = JobRecord(
        job_id="job_b",
        phase="queued",
        review_status="none",
        name="Beta",
        skip_subtitle=True,
        auto_approve=False,
    )
    repo.save_job("project-001", record_b)
    time.sleep(0.05)  # 确保 mtime 有差异
    record_a = JobRecord(
        job_id="job_a",
        phase="queued",
        review_status="none",
        name="Alpha",
        skip_subtitle=False,
        auto_approve=True,
    )
    repo.save_job("project-001", record_a)

    result = repo.list_jobs("project-001")

    # mtime 升序：job_b 先，job_a 后
    assert len(result) == 2
    assert result[0]["job_id"] == "job_b"
    assert result[0]["display_index"] == "001"
    assert result[0]["name"] == "Beta"
    assert result[0]["skip_subtitle"] is True
    assert result[0]["auto_approve"] is False

    assert result[1]["job_id"] == "job_a"
    assert result[1]["display_index"] == "002"
    assert result[1]["name"] == "Alpha"
    assert result[1]["skip_subtitle"] is False
    assert result[1]["auto_approve"] is True


def test_list_jobs_name_skip_subtitle_auto_approve_from_record(tmp_path: Path) -> None:
    """验证 name/skip_subtitle/auto_approve 从 JobRecord 正确带出。"""
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")

    record = JobRecord(
        job_id="job-1",
        phase="queued",
        review_status="none",
        name="测试项目",
        skip_subtitle=True,
        auto_approve=True,
    )
    repo.save_job("project-001", record)

    result = repo.list_jobs("project-001")

    assert len(result) == 1
    assert result[0]["display_index"] == "001"
    assert result[0]["name"] == "测试项目"
    assert result[0]["skip_subtitle"] is True
    assert result[0]["auto_approve"] is True


def test_list_jobs_bad_json_still_gets_display_index(tmp_path: Path) -> None:
    """解析失败的兜底记录也带 display_index。"""
    import time

    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")

    # 正常 job
    record = JobRecord(job_id="job_good", phase="queued", review_status="none")
    repo.save_job("project-001", record)
    time.sleep(0.05)

    # 写入一个坏 json 文件
    jobs_dir = tmp_path / "workspace" / "projects" / "project-001" / "control" / "jobs"
    bad_path = jobs_dir / "job_bad.json"
    bad_path.write_text("this is not valid json", encoding="utf-8")

    result = repo.list_jobs("project-001")

    assert len(result) == 2
    # mtime 升序：先 good，再 bad
    assert result[0]["job_id"] == "job_good"
    assert result[0]["display_index"] == "001"

    assert result[1]["job_id"] == "job_bad"
    assert "display_index" in result[1]
    # 兜底 display_index 可任意值，这里只验证它存在
    assert result[1]["phase"] == "unknown"
