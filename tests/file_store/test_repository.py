from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.domain_core.models import JobRecord
from packages.file_store.layout import (
    AmbiguousJobError,
    WorkspaceLayout,
)
from packages.file_store.repository import FileStoreRepository


def test_create_project_layout(tmp_path: Path) -> None:
    repo = FileStoreRepository(tmp_path)

    project_root = repo.create_project("project-001")

    expected_dirs = [
        project_root / "control" / "jobs",
        project_root / "control" / "batches",
        project_root / "reviews",
        project_root / "reports",
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
            [
                {"visual_type": "unresolved"},
                {"visual_type": "blank"},
                {"visual_type": "unresolved"},
            ]
        ),
        encoding="utf-8",
    )

    result = repo.list_jobs("project-001")

    assert result[0]["asset_review_unresolved_count"] == 2


def test_list_jobs_keeps_creation_order_after_job_is_saved_again(
    tmp_path: Path,
) -> None:
    """状态保存不得改变 Job 的创建顺序和 display_index (#354)。"""
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")

    first = JobRecord(
        job_id="job_z",
        created_at="2026-07-26T01:00:00+00:00",
        phase="queued",
        review_status="none",
    )
    second = JobRecord(
        job_id="job_a",
        created_at="2026-07-26T01:00:01+00:00",
        phase="queued",
        review_status="none",
    )
    repo.save_job("project-001", first)
    repo.save_job("project-001", second)

    before_save = repo.list_jobs("project-001")

    first.phase = "script_generating"
    repo.save_job("project-001", first)
    after_save = repo.list_jobs("project-001")

    assert [(item["job_id"], item["display_index"]) for item in before_save] == [
        ("job_z", "001"),
        ("job_a", "002"),
    ]
    assert [(item["job_id"], item["display_index"]) for item in after_save] == [
        ("job_z", "001"),
        ("job_a", "002"),
    ]


def test_list_jobs_gives_legacy_records_deterministic_compatibility_order(
    tmp_path: Path,
) -> None:
    """Historical Jobs without created_at remain stable across subsequent saves."""
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")
    legacy_z = JobRecord(
        job_id="job_z",
        phase="queued",
        review_status="none",
    )
    legacy_a = JobRecord(
        job_id="job_a",
        phase="queued",
        review_status="none",
    )
    repo.save_job("project-001", legacy_z)
    repo.save_job("project-001", legacy_a)

    before_save = repo.list_jobs("project-001")
    legacy_z.phase = "script_generating"
    repo.save_job("project-001", legacy_z)
    after_save = repo.list_jobs("project-001")

    assert [item["job_id"] for item in before_save] == ["job_a", "job_z"]
    assert [item["job_id"] for item in after_save] == ["job_a", "job_z"]


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
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")

    # 坏 json 文件 (先创建的)
    jobs_dir = tmp_path / "workspace" / "projects" / "project-001" / "control" / "jobs"
    bad_path = jobs_dir / "job_bad.json"
    bad_path.write_text("this is not valid json", encoding="utf-8")

    # 正常 job (后创建的)
    record = JobRecord(job_id="job_good", phase="queued", review_status="none")
    repo.save_job("project-001", record)

    result = repo.list_jobs("project-001")

    assert len(result) == 2
    # creation order: bad was created first → 001, good later → 002
    assert result[0]["job_id"] == "job_bad"
    assert "display_index" in result[0]
    assert result[0]["phase"] == "unknown"

    assert result[1]["job_id"] == "job_good"
    assert result[1]["display_index"] == "002"


# ——— WorkspaceLayout seam 接入 ———


def test_repository_exposes_workspace_layout_attribute(tmp_path: Path) -> None:
    """``repo.layout`` is the read-only seam for project-tree paths (#357)."""
    repo = FileStoreRepository(tmp_path)
    assert isinstance(repo.layout, WorkspaceLayout)
    assert repo.layout.root == tmp_path


def test_repository_does_not_expose_public_root_attribute(tmp_path: Path) -> None:
    """``root`` is no longer a public attribute on the repository (#357).

    Production callers must route through ``repo.layout`` so the layout
    seam remains the single source of truth.
    """
    repo = FileStoreRepository(tmp_path)
    assert not hasattr(repo, "root")


# ——— find_project_for_job ———


def test_find_project_for_job_returns_none_when_no_project_owns_it(
    tmp_path: Path,
) -> None:
    """No project directory holds the requested job_id → ``None`` (#357).

    The 404 / 'job not found' route path uses this branch.
    """
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")
    repo.save_job(
        "project-001",
        JobRecord(job_id="other-job", phase="queued", review_status="none"),
    )

    assert repo.find_project_for_job("missing-job") is None


def test_find_project_for_job_returns_unique_owner(tmp_path: Path) -> None:
    """A single project owns the job → that project_id is returned (#357)."""
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")
    repo.create_project("project-002")
    repo.save_job(
        "project-002",
        JobRecord(job_id="shared-job", phase="queued", review_status="none"),
    )

    assert repo.find_project_for_job("shared-job") == "project-002"


def test_find_project_for_job_raises_when_two_projects_claim_same_id(
    tmp_path: Path,
) -> None:
    """Two projects with the same job_id → ``AmbiguousJobError`` (#357).

    The 409 / 'AMBIGUOUS_JOB_ID' route path uses this branch.
    """
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-001")
    repo.create_project("project-002")
    repo.save_job(
        "project-001",
        JobRecord(job_id="dup-job", phase="queued", review_status="none"),
    )
    repo.save_job(
        "project-002",
        JobRecord(job_id="dup-job", phase="queued", review_status="none"),
    )

    with pytest.raises(AmbiguousJobError) as exc_info:
        repo.find_project_for_job("dup-job")

    message = str(exc_info.value)
    assert "project-001" in message
    assert "project-002" in message


def test_find_project_for_job_skips_projects_with_corrupt_records(
    tmp_path: Path,
) -> None:
    """A corrupt job record in one project must not mask the unique owner (#357)."""
    repo = FileStoreRepository(tmp_path)
    repo.create_project("project-bad")
    repo.create_project("project-good")
    # Corrupt record in project-bad — load_job raises, scan skips it.
    bad_jobs_dir = (
        tmp_path / "workspace" / "projects" / "project-bad" / "control" / "jobs"
    )
    bad_jobs_dir.mkdir(parents=True, exist_ok=True)
    (bad_jobs_dir / "shared-job.json").write_text("not valid json", encoding="utf-8")
    # Real record in project-good.
    repo.save_job(
        "project-good",
        JobRecord(job_id="shared-job", phase="queued", review_status="none"),
    )

    assert repo.find_project_for_job("shared-job") == "project-good"


def test_find_project_for_job_no_projects_at_all(tmp_path: Path) -> None:
    """Empty workspace → ``None`` (no projects to scan)."""
    repo = FileStoreRepository(tmp_path)

    assert repo.find_project_for_job("anything") is None
