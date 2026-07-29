"""Tests for JobTickService logging (issue #385)."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from packages.domain_core.models import (
    ArtifactPointer,
    JobRecord,
    PhaseExecutionState,
)
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import JobTickService
from packages.pipeline_services.phase_orchestrator import PhaseOrchestrator


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def mock_repo(tmp_root: Path) -> Mock:
    repo = Mock(spec=FileStoreRepository)
    repo.layout = Mock()
    repo.layout.job_runtime_dir.return_value = tmp_root / "runtime"
    repo.layout.job_record_path.return_value = tmp_root / "job.json"
    return repo


@pytest.fixture
def mock_orchestrator() -> Mock:
    return Mock(spec=PhaseOrchestrator)


def _make_record(phase: str = "script_generating") -> JobRecord:
    return JobRecord(
        job_id="job-001",
        project_id="proj-001",
        product="demo",
        phase=phase,  # type: ignore[arg-type]
        review_status="none",  # type: ignore[arg-type]
        execution=PhaseExecutionState(status="pending", current_attempt=0),
    )


def test_tick_logs_start_and_transition(
    caplog: pytest.LogCaptureFixture,
    tmp_root: Path,
    mock_repo: Mock,
    mock_orchestrator: Mock,
) -> None:
    """tick() emits a start log and a phase-transition log with job_id."""
    caplog.set_level(logging.INFO)

    record = _make_record("script_generating")
    mock_repo.load_job.return_value = record
    mock_orchestrator.run_phase.return_value = [
        ArtifactPointer(
            kind="script",
            relative_path="script.txt",
            url="/workspace/script.txt",
            size_bytes=0,
        )
    ]

    svc = JobTickService(orchestrator=mock_orchestrator, repo=mock_repo)
    svc.tick(
        "proj-001",
        "job-001",
        "demo",
        root_dir=tmp_root,
        project_dir=tmp_root / "project",
    )

    start_logs = [r for r in caplog.records if "tick start" in r.message]
    assert start_logs, "expected tick start log"
    assert "job-001" in start_logs[0].message
    assert start_logs[0].job_id == "job-001"  # type: ignore[attr-defined]
    assert start_logs[0].levelno == logging.INFO

    transition_logs = [r for r in caplog.records if "transition" in r.message]
    assert transition_logs, "expected transition log"
    assert "job-001" in transition_logs[0].message
    assert transition_logs[0].levelno == logging.INFO


def test_tick_logs_retry_path(
    caplog: pytest.LogCaptureFixture,
    tmp_root: Path,
    mock_repo: Mock,
    mock_orchestrator: Mock,
) -> None:
    """Retryable failure emits a retry warning with backoff and attempt count."""
    caplog.set_level(logging.WARNING)

    record = _make_record("tts_generating")
    record.execution = PhaseExecutionState(
        status="pending", current_attempt=0, max_attempts=1
    )

    from packages.domain_core.models import ExecutionFailure
    from packages.domain_core.phase_execution import PhaseExecutionFailure

    mock_orchestrator.execute_phase.return_value = PhaseExecutionFailure(
        error=ExecutionFailure(
            code="MEDIA_PROCESSING_FAILED",
            message="boom",
            retryable=True,
        )
    )

    # Mirror persistence so the retry loop observes the updated execution state.
    current_record = record

    def _save_job(project_id: str, r: JobRecord) -> None:
        nonlocal current_record
        current_record = r

    def _load_job(project_id: str, job_id: str) -> JobRecord:
        return current_record

    mock_repo.save_job.side_effect = _save_job
    mock_repo.load_job.side_effect = _load_job

    svc = JobTickService(
        orchestrator=mock_orchestrator,
        repo=mock_repo,
        sleep_fn=lambda _s: None,
    )
    svc.tick(
        "proj-001",
        "job-001",
        "demo",
        root_dir=tmp_root,
        project_dir=tmp_root / "project",
    )

    retry_logs = [r for r in caplog.records if "retrying" in r.message]
    assert retry_logs, "expected retry log"
    assert "job-001" in retry_logs[0].message
    assert retry_logs[0].levelno == logging.WARNING


def test_tick_logs_transition_without_handler(
    caplog: pytest.LogCaptureFixture,
    tmp_root: Path,
    mock_repo: Mock,
    mock_orchestrator: Mock,
) -> None:
    """A lifecycle transition is logged even when no phase handler runs."""
    caplog.set_level(logging.INFO)

    record = _make_record("script_generating").model_copy(
        update={"cancellation_requested": True}
    )
    mock_repo.load_job.return_value = record

    svc = JobTickService(orchestrator=mock_orchestrator, repo=mock_repo)
    summary = svc.tick(
        "proj-001",
        "job-001",
        "demo",
        root_dir=tmp_root,
        project_dir=tmp_root / "project",
    )

    assert summary.to_phase == "cancelled"
    transition_logs = [r for r in caplog.records if "transition" in r.message]
    assert transition_logs, "expected handler-free transition log"
    assert "script_generating -> cancelled" in transition_logs[0].message
    assert "job-001" in transition_logs[0].message


def test_tick_logs_handler_exception_with_traceback(
    caplog: pytest.LogCaptureFixture,
    tmp_root: Path,
    mock_repo: Mock,
    mock_orchestrator: Mock,
) -> None:
    """A terminal handler exception keeps its diagnostic message and traceback."""
    caplog.set_level(logging.ERROR)

    record = _make_record("script_generating")
    record.execution = PhaseExecutionState(
        status="retrying", current_attempt=1, max_attempts=1
    )
    mock_repo.load_job.return_value = record
    mock_orchestrator.run_phase.side_effect = RuntimeError("provider exploded")

    svc = JobTickService(orchestrator=mock_orchestrator, repo=mock_repo)
    summary = svc.tick(
        "proj-001",
        "job-001",
        "demo",
        root_dir=tmp_root,
        project_dir=tmp_root / "project",
    )

    assert summary.to_phase == "failed"
    failure_logs = [r for r in caplog.records if "handler failed" in r.message]
    assert failure_logs
    assert "provider exploded" in failure_logs[0].message
    assert failure_logs[0].exc_info is not None


def test_tick_logs_structured_handler_exception_with_traceback(
    caplog: pytest.LogCaptureFixture,
    tmp_root: Path,
    mock_repo: Mock,
    mock_orchestrator: Mock,
) -> None:
    """A structured phase failure retains the provider exception traceback."""
    from packages.domain_core.models import ExecutionFailure
    from packages.domain_core.phase_execution import PhaseExecutionFailure

    caplog.set_level(logging.ERROR)
    record = _make_record("tts_generating")
    record.execution = PhaseExecutionState(
        status="retrying", current_attempt=1, max_attempts=1
    )
    mock_repo.load_job.return_value = record
    try:
        raise RuntimeError("structured provider exploded")
    except RuntimeError as exc:
        cause = exc
    mock_orchestrator.execute_phase.return_value = PhaseExecutionFailure.from_exception(
        error=ExecutionFailure(
            code="TTS_SYNTHESIS_FAILED",
            message=str(cause),
            retryable=True,
        ),
        cause=cause,
    )

    svc = JobTickService(orchestrator=mock_orchestrator, repo=mock_repo)
    summary = svc.tick(
        "proj-001",
        "job-001",
        "demo",
        root_dir=tmp_root,
        project_dir=tmp_root / "project",
    )

    assert summary.to_phase == "failed"
    failure_logs = [r for r in caplog.records if "handler failed" in r.message]
    assert failure_logs
    assert "structured provider exploded" in failure_logs[0].message
    assert failure_logs[0].exc_info is not None
