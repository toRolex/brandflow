from __future__ import annotations

from typing import Literal

from packages.domain_core.worker_protocol import WorkerReport

Outcome = Literal["accept", "orphan"]


def choose_report_outcome(
    current: dict[str, str] | None,
    report: WorkerReport,
) -> Outcome:
    """Determine whether a worker's report should be accepted or orphaned.

    ``current`` is the entry from the dispatcher's ``current_attempts`` dict
    for this task_id (or *None* if the dispatcher has no record of it).

    Returns ``"accept"`` when the report's *attempt_id* and *lease_id* both
    match the tracked values, and ``"orphan"`` otherwise.
    """
    if current is None:
        return "orphan"
    if current["attempt_id"] != report.attempt_id:
        return "orphan"
    if current["lease_id"] != report.lease_id:
        return "orphan"
    return "accept"
