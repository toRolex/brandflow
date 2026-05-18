from __future__ import annotations

from apps.control_plane.services.reconcile import choose_report_outcome
from packages.domain_core.worker_protocol import WorkerReport


def _make_report(
    attempt_id: str = "attempt-abc",
    lease_id: str = "lease-xyz",
    task_id: str = "task-j1",
) -> WorkerReport:
    return WorkerReport(
        worker_id="w1",
        project_id="p1",
        job_id="j1",
        task_id=task_id,
        attempt_id=attempt_id,
        lease_id=lease_id,
        status="succeeded",
        started_at="2026-05-18T00:00:00Z",
        finished_at="2026-05-18T00:01:00Z",
    )


def test_current_is_none_returns_orphan() -> None:
    """A report for a task the dispatcher has never seen is orphaned."""
    report = _make_report()
    outcome = choose_report_outcome(current=None, report=report)
    assert outcome == "orphan"


def test_attempt_id_mismatch_returns_orphan() -> None:
    """A report with a stale attempt_id is orphaned."""
    current = {"attempt_id": "attempt-current", "lease_id": "lease-xyz"}
    report = _make_report(attempt_id="attempt-stale")
    outcome = choose_report_outcome(current=current, report=report)
    assert outcome == "orphan"


def test_lease_id_mismatch_returns_orphan() -> None:
    """A report with a stale lease_id is orphaned."""
    current = {"attempt_id": "attempt-abc", "lease_id": "lease-current"}
    report = _make_report(lease_id="lease-stale")
    outcome = choose_report_outcome(current=current, report=report)
    assert outcome == "orphan"


def test_all_match_returns_accept() -> None:
    """A report matching current attempt/lease is accepted."""
    current = {"attempt_id": "attempt-abc", "lease_id": "lease-xyz"}
    report = _make_report()
    outcome = choose_report_outcome(current=current, report=report)
    assert outcome == "accept"


def test_extra_current_keys_ignored() -> None:
    """Current dict may contain extra keys beyond attempt_id/lease_id."""
    current = {
        "project_id": "p1",
        "job_id": "j1",
        "attempt_id": "attempt-abc",
        "lease_id": "lease-xyz",
        "worker_id": "w1",
    }
    report = _make_report()
    outcome = choose_report_outcome(current=current, report=report)
    assert outcome == "accept"
