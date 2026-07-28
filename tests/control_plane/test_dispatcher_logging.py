"""Tests for Dispatcher logging (issue #385)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from apps.control_plane.services.dispatch import Dispatcher
from packages.domain_core.models import JobRecord, PhaseExecutionState
from packages.file_store.repository import FileStoreRepository


def _make_record(phase: str = "script_generating") -> JobRecord:
    return JobRecord(
        job_id="job-001",
        project_id="proj-001",
        product="demo",
        phase=phase,  # type: ignore[arg-type]
        review_status="none",  # type: ignore[arg-type]
        execution=PhaseExecutionState(status="pending", current_attempt=0),
    )


def test_poll_logs_dispatch(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """poll() emits an INFO log when dispatching a task to a worker."""
    caplog.set_level(logging.INFO)

    projects_dir = tmp_path / "workspace" / "projects"
    project_dir = projects_dir / "proj-001"
    jobs_dir = project_dir / "control" / "jobs"
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "job-001.json").write_text(
        _make_record("script_generating").model_dump_json(), encoding="utf-8"
    )

    repo = Mock(spec=FileStoreRepository)
    repo.layout = Mock()
    repo.layout.projects_dir.return_value = projects_dir
    repo.list_jobs.return_value = [{"job_id": "job-001"}]
    repo.load_job.return_value = _make_record("script_generating")

    dispatcher = Dispatcher(repo)
    result = dispatcher.poll("worker-001")

    assert result["command"] == "run_task"
    dispatch_logs = [r for r in caplog.records if "dispatching" in r.message]
    assert dispatch_logs
    assert "job-001" in dispatch_logs[0].message
    assert "script_generating" in dispatch_logs[0].message
    assert "worker-001" in dispatch_logs[0].message
    assert dispatch_logs[0].levelno == logging.INFO


def test_accept_report_logs_orphan(caplog: pytest.LogCaptureFixture) -> None:
    """accept_report() emits a WARNING for an unknown task_id."""
    caplog.set_level(logging.WARNING)

    repo = Mock(spec=FileStoreRepository)
    dispatcher = Dispatcher(repo)
    accepted = dispatcher.accept_report("unknown-task", "attempt-1", "lease-1")

    assert accepted is False
    orphan_logs = [r for r in caplog.records if "orphan" in r.message]
    assert orphan_logs, "expected orphan report warning"
    assert "unknown-task" in orphan_logs[0].message
    assert orphan_logs[0].levelno == logging.WARNING
