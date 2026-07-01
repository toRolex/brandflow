"""Tests for _compute_transition pure state machine."""

from __future__ import annotations

from typing import Any

import pytest

from packages.domain_core.models import JobRecord, ArtifactPointer
from packages.pipeline_services.job_tick_service import (
    HANDLED_PHASES,
    REVIEW_PHASES,
    TickAction,
    _compute_transition,
    _transition_after_artifacts,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_record(
    phase: str = "queued",
    last_error: str = "",
    review_status: str = "none",
    skip_subtitle: bool = False,
    auto_approve: bool = False,
) -> JobRecord:
    """Factory for concise test construction."""
    return JobRecord(
        job_id="test-job",
        project_id="proj-001",
        product="羊肚菌",
        phase=phase,  # type: ignore[arg-type]
        review_status=review_status,  # type: ignore[arg-type]
        last_error=last_error,
        skip_subtitle=skip_subtitle,
        auto_approve=auto_approve,
    )


def _next(phase: str) -> str:
    """Return the expected next phase (matching domain_core.state.next_phase)."""
    order = [
        "queued",
        "script_generating",
        "script_review",
        "tts_generating",
        "tts_review",
        "subtitle_generating",
        "asset_retrieving",
        "asset_review",
        "video_rendering",
        "final_review",
        "completed",
    ]
    idx = order.index(phase)
    if idx >= len(order) - 1:
        return "completed"
    return order[idx + 1]


# ---------------------------------------------------------------------------
# 1. queued → script_generating
# ---------------------------------------------------------------------------


class TestQueued:
    def test_queued_routes_to_script_generating_handler(self) -> None:
        action = _compute_transition(make_record(phase="queued"), ())
        assert action.run_handler is True
        assert action.handler_phase == "script_generating"
        assert action.new_phase is None
        assert action.new_review_status is None


# ---------------------------------------------------------------------------
# 2. Review phases
# ---------------------------------------------------------------------------


class TestReviewApproved:
    """review_status == "approved" → advance to next phase."""

    @pytest.mark.parametrize(
        "phase",
        ["script_review", "tts_review", "asset_review", "final_review"],
    )
    def test_approved_advances(self, phase: str) -> None:
        action = _compute_transition(
            make_record(phase=phase, review_status="approved"),
            (),
        )
        assert action.new_phase == _next(phase)
        assert action.new_review_status == "none"
        assert action.run_handler is False


class TestReviewPending:
    """review_status == "pending" (or "none") → skip (empty TickAction)."""

    @pytest.mark.parametrize(
        ("phase", "review_status"),
        [
            ("script_review", "pending"),
            ("tts_review", "pending"),
            ("asset_review", "pending"),
            ("final_review", "pending"),
            ("script_review", "none"),
            ("tts_review", "none"),
            ("asset_review", "none"),
            ("final_review", "none"),
        ],
    )
    def test_pending_returns_empty_action(self, phase: str, review_status: str) -> None:
        action = _compute_transition(
            make_record(phase=phase, review_status=review_status),
            (),
        )
        # An empty TickAction means "skip" — no handler, no transition
        assert action.run_handler is False
        assert action.new_phase is None
        assert action.new_review_status is None


class TestReviewAutoApprove:
    """auto_approve=True + not yet approved → auto-advance."""

    def test_auto_approve_no_handler_advances(self) -> None:
        """script_review and asset_review have no handler → direct advance."""
        action = _compute_transition(
            make_record(phase="script_review", auto_approve=True),
            (),
        )
        assert action.new_phase == _next("script_review")
        assert action.new_review_status == "approved"
        assert action.run_handler is False

    def test_auto_approve_no_handler_asset_review(self) -> None:
        action = _compute_transition(
            make_record(phase="asset_review", auto_approve=True),
            (),
        )
        assert action.new_phase == _next("asset_review")
        assert action.new_review_status == "approved"
        assert action.run_handler is False

    def test_auto_approve_with_handler_tts_review(self) -> None:
        """tts_review and final_review have handlers → run_handler=True."""
        action = _compute_transition(
            make_record(phase="tts_review", auto_approve=True),
            (),
        )
        assert action.run_handler is True
        assert action.handler_phase == "tts_review"
        assert action.new_phase == _next("tts_review")
        assert action.new_review_status == "approved"
        assert action.review_event == {"event": "auto_approve"}

    def test_auto_approve_with_handler_final_review(self) -> None:
        action = _compute_transition(
            make_record(phase="final_review", auto_approve=True),
            (),
        )
        assert action.run_handler is True
        assert action.handler_phase == "final_review"
        assert action.new_phase == _next("final_review")
        assert action.new_review_status == "approved"
        assert action.review_event == {"event": "auto_approve"}

    def test_auto_approve_with_approved_does_not_reapprove(self) -> None:
        """Already-approved reviews should advance, not re-auto-approve."""
        action = _compute_transition(
            make_record(phase="script_review", review_status="approved", auto_approve=True),
            (),
        )
        # The "approved" check precedes the auto_approve check
        assert action.new_phase == _next("script_review")
        assert action.new_review_status == "none"
        assert action.run_handler is False

    def test_auto_approve_with_pending_does_not_reapprove(self) -> None:
        """Already-pending reviews should wait, not auto-approve."""
        action = _compute_transition(
            make_record(phase="script_review", review_status="pending", auto_approve=True),
            (),
        )
        assert action.run_handler is False
        assert action.new_phase is None


# ---------------------------------------------------------------------------
# 3. Subtitle skip
# ---------------------------------------------------------------------------


class TestSubtitleSkip:
    def test_subtitle_skip_advances(self) -> None:
        action = _compute_transition(
            make_record(phase="subtitle_generating", skip_subtitle=True),
            (),
        )
        assert action.new_phase == _next("subtitle_generating")
        assert action.run_handler is False


# ---------------------------------------------------------------------------
# 4. Handler execution — pre-handler state
# ---------------------------------------------------------------------------


class TestHandlerExecution:
    """Phases in HANDLED_PHASES with no artifacts → run_handler."""

    @pytest.mark.parametrize(
        "phase",
        [
            p for p in HANDLED_PHASES
            if p not in REVIEW_PHASES
            and p not in ("video_rendering", "subtitle_generating", "asset_retrieving")
        ],
    )
    def test_handled_phases_return_run_handler(self, phase: str) -> None:
        action = _compute_transition(make_record(phase=phase), ())
        assert action.run_handler is True
        assert action.handler_phase == phase
        assert action.new_phase is None


# ---------------------------------------------------------------------------
# 5. Post-handler: artifacts produced → advance
# ---------------------------------------------------------------------------


class TestArtifactsProduced:
    def test_advance_on_artifacts(self) -> None:
        action = _compute_transition(
            make_record(phase="script_generating"),
            ({"kind": "script", "relative_path": "script.txt"},),
        )
        assert action.new_phase == _next("script_generating")
        assert action.run_handler is False

    def test_advance_to_review_sets_pending(self) -> None:
        """Advancing into a review phase sets review_status="pending"."""
        action = _compute_transition(
            make_record(phase="tts_generating"),
            ({"kind": "audio", "relative_path": "audio.wav"},),
        )
        assert action.new_phase == "tts_review"
        assert action.new_review_status == "pending"

    def test_any_artifacts_triggers_review_pending(self) -> None:
        """Any transition whose target is a review phase sets pending."""
        action = _compute_transition(
            make_record(phase="asset_retrieving"),
            ({"kind": "clip", "relative_path": "clip.mp4"},),
        )
        assert action.new_phase == "asset_review"
        assert action.new_review_status == "pending"

    def test_terminal_phase_returns_completed(self) -> None:
        """Advancing past final_review yields 'completed'."""
        action = _compute_transition(
            make_record(phase="final_review", review_status="approved"),
            (),
        )
        assert action.new_phase == "completed"


# ---------------------------------------------------------------------------
# 6. Post-handler: no artifacts for video_rendering
# ---------------------------------------------------------------------------


class TestVideoRenderingNoArtifacts:
    def test_first_failure_retries(self) -> None:
        """No artifacts + no prior last_error → retry next tick."""
        action = _transition_after_artifacts(
            make_record(phase="video_rendering", last_error=""),
            (),
        )
        assert action.new_phase is None
        assert action.run_handler is False
        assert "retry" in action.message.lower()

    def test_second_failure_marks_failed(self) -> None:
        """No artifacts + prior video_rendering error → mark as failed."""
        action = _transition_after_artifacts(
            make_record(phase="video_rendering", last_error="video_rendering failed to produce artifacts"),
            (),
        )
        assert action.new_phase == "failed"
        assert action.run_handler is False


# ---------------------------------------------------------------------------
# 7. Post-handler: no artifacts for subtitle_generating
# ---------------------------------------------------------------------------


class TestSubtitleGeneratingNoArtifacts:
    def test_stays_in_phase(self) -> None:
        action = _transition_after_artifacts(
            make_record(phase="subtitle_generating"),
            (),
        )
        assert action.new_phase is None
        assert action.run_handler is False
        assert "staying" in action.message.lower()


# ---------------------------------------------------------------------------
# 8. Post-handler: auto-advance on no artifacts for non-critical phases
# ---------------------------------------------------------------------------


class TestAutoAdvanceNoArtifacts:
    def test_asset_retrieving_auto_advances(self) -> None:
        action = _transition_after_artifacts(
            make_record(phase="asset_retrieving"),
            (),
        )
        assert action.new_phase == _next("asset_retrieving")
        assert action.run_handler is False


# ---------------------------------------------------------------------------
# 9. Terminal phases skip
# ---------------------------------------------------------------------------


class TestTerminalPhases:
    @pytest.mark.parametrize("phase", ["completed", "failed", "cancelled", "paused"])
    def test_terminal_returns_empty_action(self, phase: str) -> None:
        action = _compute_transition(make_record(phase=phase), ())
        assert action.run_handler is False
        assert action.new_phase is None
        assert action.new_review_status is None

    @pytest.mark.parametrize("phase", ["completed", "failed", "cancelled", "paused"])
    def test_terminal_with_artifacts_still_skips(self, phase: str) -> None:
        """Even with artifacts, terminal phases should not transition."""
        action = _compute_transition(
            make_record(phase=phase),
            ({"kind": "stale", "relative_path": "x"},),
        )
        assert action.run_handler is False
        assert action.new_phase is None


# ---------------------------------------------------------------------------
# 10. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_tick_action_defaults(self) -> None:
        """TickAction default constructor creates an empty action."""
        action = TickAction()
        assert action.new_phase is None
        assert action.new_review_status is None
        assert action.run_handler is False
        assert action.handler_phase is None
        assert action.review_event is None
        assert action.message == ""

    def test_review_phase_sets_handler_phase_when_in_handled(self) -> None:
        """tts_review and final_review are in both REVIEW and HANDLED sets."""
        assert "tts_review" in REVIEW_PHASES
        assert "tts_review" in HANDLED_PHASES
        assert "final_review" in REVIEW_PHASES
        assert "final_review" in HANDLED_PHASES

    def test_non_review_handled_is_not_in_review(self) -> None:
        assert "script_generating" in HANDLED_PHASES
        assert "script_generating" not in REVIEW_PHASES

    def test_override_status_is_waiting_without_auto_approve(self) -> None:
        action = _compute_transition(
            make_record(phase="script_review", review_status="overridden"),
            (),
        )
        # "overridden" is neither "approved" nor "pending" / "none"
        # It's not in the auto_approve check condition either
        assert action.run_handler is False
        assert action.new_phase is None

    def test_next_phase_safe_returns_completed(self) -> None:
        """Completed phase has no next phase."""
        from packages.pipeline_services.job_tick_service import _safe_next
        assert _safe_next("completed") == "completed"
