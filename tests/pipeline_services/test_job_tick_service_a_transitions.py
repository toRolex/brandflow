"""Tests for _compute_transition pure state machine."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from packages.domain_core.models import (
    REVIEW_PHASES,
    ArtifactPointer,
    JobRecord,
    PhaseExecutionState,
)
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import (
    HANDLED_PHASES,
    _compute_transition,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _persistent_repo(initial: JobRecord) -> Mock:
    """Return a mock FileStoreRepository that tracks state across saves/reloads.

    Every ``load_job`` returns a model-copy of the latest saved record, and
    every ``save_job`` updates the backing store.  This is required for any
    test that exercises ``tick()`` because the chain loop reloads between
    steps.
    """
    repo = Mock(spec=FileStoreRepository)
    latest: list[JobRecord] = [initial]

    def _load(project_id: str, job_id: str) -> JobRecord:
        return latest[0].model_copy()

    def _save(project_id: str, rec: JobRecord) -> None:
        latest[0] = rec

    repo.load_job.side_effect = _load
    repo.save_job.side_effect = _save
    return repo


def make_record(
    phase: str = "queued",
    review_status: str = "none",
    skip_subtitle: bool = False,
    auto_approve: bool = False,
    review_strategy: str = "review_each",
    mode: str = "generate",
    manual_script: str = "",
    execution: PhaseExecutionState | None = None,
    artifacts: list[ArtifactPointer] | None = None,
    pause_requested: bool = False,
    cancellation_requested: bool = False,
    asset_collection_status: str = "not_started",
) -> JobRecord:
    """Factory for concise test construction."""
    return JobRecord(
        job_id="test-job",
        project_id="proj-001",
        product="羊肚菌",
        phase=phase,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        review_status=review_status,  # type: ignore[arg-type]
        skip_subtitle=skip_subtitle,
        auto_approve=auto_approve,
        review_strategy=review_strategy,  # type: ignore[arg-type]
        manual_script=manual_script,
        execution=execution if execution is not None else PhaseExecutionState(),
        artifacts=artifacts if artifacts is not None else [],
        pause_requested=pause_requested,
        cancellation_requested=cancellation_requested,
        asset_collection_status=asset_collection_status,  # type: ignore[arg-type]
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
        "montage_assembling",
        "video_rendering",
        "final_rendering",
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

    def test_pause_request_stops_at_the_safe_transition_boundary(self) -> None:
        action = _compute_transition(
            make_record(phase="tts_generating", pause_requested=True), ()
        )
        assert action.new_phase == "paused"
        assert action.run_handler is False

    def test_cancellation_request_wins_over_pause_request(self) -> None:
        action = _compute_transition(
            make_record(
                phase="tts_generating",
                pause_requested=True,
                cancellation_requested=True,
            ),
            (),
        )
        assert action.new_phase == "cancelled"


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


class TestReviewStrategy:
    """fast_output auto-approves all four review phases (script, TTS, asset, final)."""

    def test_fast_output_advances_script_review(self) -> None:
        action = _compute_transition(
            make_record(phase="script_review", review_strategy="fast_output"),
            (),
        )
        assert action.new_phase == _next("script_review")
        assert action.new_review_status == "approved"
        assert action.run_handler is False

    def test_fast_output_auto_approves_asset_review(self) -> None:
        """asset_review has no handler → auto-approval advances without running one."""
        action = _compute_transition(
            make_record(phase="asset_review", review_strategy="fast_output"),
            (),
        )
        assert action.new_phase == _next("asset_review")
        assert action.new_review_status == "approved"
        assert action.run_handler is False

    def test_fast_output_auto_approves_tts_review(self) -> None:
        """tts_review and final_review have handlers → run_handler=True."""
        action = _compute_transition(
            make_record(phase="tts_review", review_strategy="fast_output"),
            (),
        )
        assert action.run_handler is True
        assert action.handler_phase == "tts_review"
        assert action.new_phase == _next("tts_review")
        assert action.new_review_status == "approved"
        assert action.review_event == {"event": "auto_approve"}

    def test_fast_output_auto_approves_final_review(self) -> None:
        """final_review has no handler → auto-approval advances without running one."""
        action = _compute_transition(
            make_record(phase="final_review", review_strategy="fast_output"),
            (),
        )
        assert action.run_handler is False
        assert action.new_phase == _next("final_review")
        assert action.new_review_status == "approved"

    def test_fast_output_with_approved_does_not_reapprove(self) -> None:
        """Already-approved reviews should advance, not re-auto-approve."""
        action = _compute_transition(
            make_record(
                phase="script_review",
                review_status="approved",
                review_strategy="fast_output",
            ),
            (),
        )
        # The "approved" check precedes the auto_approve check
        assert action.new_phase == _next("script_review")
        assert action.new_review_status == "none"
        assert action.run_handler is False

    def test_fast_output_with_pending_does_not_reapprove(self) -> None:
        """Already-pending reviews should wait, not auto-approve."""
        action = _compute_transition(
            make_record(
                phase="script_review",
                review_status="pending",
                review_strategy="fast_output",
            ),
            (),
        )
        assert action.run_handler is False
        assert action.new_phase is None

    def test_fast_output_with_skip_subtitle_chains_past_subtitle(self) -> None:
        """auto_approve + skip_subtitle should skip over subtitle_generating."""
        # tts_review → normally → subtitle_generating, but with skip_subtitle
        # should go directly to asset_retrieving
        action = _compute_transition(
            make_record(
                phase="tts_review", review_strategy="fast_output", skip_subtitle=True
            ),
            (),
        )
        assert action.new_phase == "asset_retrieving"  # skips subtitle_generating
        assert action.new_review_status == "approved"

    def test_fast_output_skip_subtitle_auto_approves_asset_review(self) -> None:
        action = _compute_transition(
            make_record(
                phase="asset_review", review_strategy="fast_output", skip_subtitle=True
            ),
            (),
        )
        assert action.new_phase == _next("asset_review")
        assert action.new_review_status == "approved"

    def test_fast_output_no_skip_subtitle_goes_to_subtitle(self) -> None:
        """Without skip_subtitle, auto_approve should still go to subtitle."""
        action = _compute_transition(
            make_record(phase="tts_review", review_strategy="fast_output"),
            (),
        )
        assert action.new_phase == "subtitle_generating"
        assert action.new_review_status == "approved"


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
        sorted(
            p
            for p in HANDLED_PHASES
            if p not in REVIEW_PHASES
            and p not in ("video_rendering", "subtitle_generating", "asset_retrieving")
        ),
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
