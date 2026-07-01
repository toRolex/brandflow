"""Pure-function state machine for job phase transitions.

Defines types (TickAction, TickSummary, PhaseExecutionError) and the pure
transition function _compute_transition that decides what should happen next
given a JobRecord and the artifacts produced by the current phase handler.

This module has zero I/O and zero side effects — all transition logic is
contained in a single referentially transparent function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from packages.domain_core.models import JobRecord
from packages.domain_core.state import next_phase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REVIEW_PHASES: frozenset[str] = frozenset(
    {"script_review", "tts_review", "asset_review", "final_review"}
)

HANDLED_PHASES: frozenset[str] = frozenset({
    "script_generating",
    "tts_generating",
    "tts_review",
    "subtitle_generating",
    "asset_retrieving",
    "video_rendering",
    "final_review",
})

_TERMINAL_PHASES: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "paused"}
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class TickAction:
    """Pure-data description of what should happen next for a job.

    Fields
    ------
    new_phase : str | None
        The phase to transition into (None = stay in current phase).
    new_review_status : str | None
        New review status to set after the transition (None = unchanged).
    run_handler : bool
        True when the caller should execute the phase handler.
    handler_phase : str | None
        Which phase handler to run (only meaningful when *run_handler* is
        True).  ``None`` means the current phase.
    review_event : dict | None
        Optional review event payload to persist when the transition is
        the result of an auto-approve.
    message : str
        Human-readable description of the decision.
    """

    new_phase: str | None = None
    new_review_status: str | None = None
    run_handler: bool = False
    handler_phase: str | None = None
    review_event: dict | None = None
    message: str = ""


@dataclass
class TickSummary:
    """Public result returned to callers of the tick workflow."""

    action: str  # "skipped" | "advanced" | "completed" | "failed"
    from_phase: str
    to_phase: str
    message: str = ""


class PhaseExecutionError(Exception):
    """Raised when a phase handler fails with an unexpected error."""

    def __init__(self, job_id: str, phase: str, message: str, cause: Exception):
        self.job_id = job_id
        self.phase = phase
        self.cause = cause
        super().__init__(f"[{job_id}] {phase}: {message}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_next(phase: str) -> str:
    """Return the next phase after *phase*, or ``"completed"`` if already at the end."""
    try:
        return next_phase(phase)
    except ValueError:
        return "completed"


# ---------------------------------------------------------------------------
# Pure transition function
# ---------------------------------------------------------------------------


def _compute_transition(
    record: JobRecord,
    artifacts: tuple[Any, ...],
) -> TickAction:
    """Pure function: decides what to do next given current state.

    No I/O, no side effects.  Returns a :class:`TickAction` describing the
    transition.

    Parameters
    ----------
    record : JobRecord
        The current job state.
    artifacts : tuple
        The artifacts produced by the phase handler.  An empty tuple
        means either (a) the handler has not been invoked yet, or (b)
        the handler ran but produced no artifacts — the function
        encodes the distinction implicitly via per-phase rules.
    """
    phase = record.phase

    # ------------------------------------------------------------------
    # 1. Terminal states — nothing to do
    # ------------------------------------------------------------------
    if phase in _TERMINAL_PHASES:
        return TickAction()

    # ------------------------------------------------------------------
    # 2. Review phases
    # ------------------------------------------------------------------
    if phase in REVIEW_PHASES:
        # 2a. Already approved → advance, reset review_status
        if record.review_status == "approved":
            return TickAction(
                new_phase=_safe_next(phase),
                new_review_status="none",
                message=f"advanced past approved review {phase}",
            )

        # 2b. Auto-approve — approve without waiting for human
        if record.auto_approve and record.review_status not in ("approved", "pending"):
            if phase in HANDLED_PHASES:
                return TickAction(
                    run_handler=True,
                    handler_phase=phase,
                    new_phase=_safe_next(phase),
                    new_review_status="approved",
                    review_event={"event": "auto_approve"},
                    message=f"auto-approve {phase} (has handler)",
                )
            return TickAction(
                new_phase=_safe_next(phase),
                new_review_status="approved",
                message=f"auto-approve {phase} (no handler)",
            )

        # 2c. Waiting for human review
        return TickAction(message=f"waiting for human review on {phase}")

    # ------------------------------------------------------------------
    # 3. Subtitle skip — jump over subtitle_generating
    # ------------------------------------------------------------------
    if phase == "subtitle_generating" and record.skip_subtitle:
        return TickAction(
            new_phase=_safe_next(phase),
            message="skip subtitle_generating",
        )

    # ------------------------------------------------------------------
    # 4. Queued → route to script_generating handler
    # ------------------------------------------------------------------
    if phase == "queued":
        return TickAction(
            run_handler=True,
            handler_phase="script_generating",
            message="queued → script_generating",
        )

    # ------------------------------------------------------------------
    # 5. Post-handler: artifacts present or phase has no handler
    #    → delegate to per-phase failure / advance logic
    # ------------------------------------------------------------------
    if artifacts or phase not in HANDLED_PHASES:
        return _transition_after_artifacts(record, artifacts)

    # ------------------------------------------------------------------
    # 6. Pre-handler: no artifacts yet, phase has a registered handler
    #    → tell the caller to run the handler
    # ------------------------------------------------------------------
    return TickAction(
        run_handler=True,
        handler_phase=phase,
        message=f"phase {phase} needs handler execution",
    )

def _transition_after_artifacts(
    record: JobRecord,
    artifacts: tuple[Any, ...],
) -> TickAction:
    """Decide transition after a phase handler produced artifacts (or not).

    Separated from ``_compute_transition`` so per-phase failure logic is
    isolated for testing.
    """
    phase = record.phase

    # 1. Artifacts produced → advance
    if artifacts:
        next_p = _safe_next(phase)
        if next_p in REVIEW_PHASES:
            return TickAction(
                new_phase=next_p,
                new_review_status="pending",
                message=f"{phase} produced artifacts, advancing to {next_p} (pending review)",
            )
        return TickAction(
            new_phase=next_p,
            message=f"{phase} produced artifacts, advancing to {next_p}",
        )

    # 2. No artifacts — per-phase failure handling
    # 2a. video_rendering: retry once, then fail
    if phase == "video_rendering":
        if "video_rendering" in (record.last_error or ""):
            return TickAction(
                new_phase="failed",
                message="video_rendering failed after retry",
            )
        return TickAction(
            message="video_rendering produced no artifacts, will retry next tick",
        )

    # 2b. subtitle_generating: stay in phase (critical — do not auto-advance)
    if phase == "subtitle_generating":
        return TickAction(
            message="subtitle_generating produced no artifacts, staying in phase",
        )

    # 2c. asset_retrieving: auto-advance on no artifacts (transitional phase)
    if phase == "asset_retrieving":
        return TickAction(
            new_phase=_safe_next(phase),
            message="asset_retrieving produced no artifacts, auto-advancing",
        )

    # 2d. Other handled phases: auto-advance (transitional or empty handler)
    if phase in HANDLED_PHASES:
        return TickAction(
            new_phase=_safe_next(phase),
            message=f"{phase} produced no artifacts, auto-advancing (fallback)",
        )

    # 2e. Fallback — auto-advance
    return TickAction(
        new_phase=_safe_next(phase),
        message=f"auto-advance from {phase} (fallback)",
    )
