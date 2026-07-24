"""Tests for _compute_transition pure state machine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from packages.domain_core.models import (
    REVIEW_PHASES,
    ArtifactPointer,
    ExecutionFailure,
    JobRecord,
    PhaseExecutionState,
)
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import (
    HANDLED_PHASES,
    JobTickService,
    TickAction,
    _compute_transition,
    _transition_after_artifacts,
)
from packages.pipeline_services.phase_orchestrator import (
    PhaseOrchestrator,
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


class TestVideoRenderingNoArtifacts:
    def test_first_failure_retries(self) -> None:
        """No artifacts + no prior execution error → retry next tick."""
        action = _transition_after_artifacts(
            make_record(phase="video_rendering"),
            (),
        )
        assert action.new_phase is None
        assert action.run_handler is False
        assert "retry" in action.message.lower()

    def test_second_failure_marks_failed(self) -> None:
        """No artifacts + prior execution error → mark as failed."""
        action = _transition_after_artifacts(
            make_record(
                phase="video_rendering",
                execution=PhaseExecutionState(
                    status="retrying",
                    current_attempt=1,
                    max_attempts=3,
                    error=ExecutionFailure(
                        code="VIDEO_RENDERING_FAILED",
                        message="video_rendering produced no artifacts.",
                        retryable=True,
                    ),
                ),
            ),
            (),
        )
        assert action.new_phase == "failed"
        assert action.run_handler is False


class TestFinalRenderingNoArtifacts:
    def test_no_artifacts_stays_in_phase(self) -> None:
        """final_rendering with no artifacts must NOT auto-advance."""
        action = _transition_after_artifacts(
            make_record(phase="final_rendering"),
            (),
        )
        assert action.new_phase is None
        assert action.run_handler is False
        assert "retry" in action.message.lower()

    def test_no_artifacts_after_error_fails(self) -> None:
        """final_rendering exhausted retry with no artifacts → failed."""
        action = _transition_after_artifacts(
            make_record(
                phase="final_rendering",
                execution=PhaseExecutionState(
                    status="retrying",
                    current_attempt=1,
                    max_attempts=3,
                    error=ExecutionFailure(
                        code="FINAL_RENDERING_FAILED",
                        message="final_rendering produced no artifacts.",
                        retryable=True,
                    ),
                ),
            ),
            (),
        )
        assert action.new_phase == "failed"
        assert action.run_handler is False
        assert "failed" in action.message.lower()


class TestMergeArtifacts:
    def test_updates_existing_kind(self) -> None:
        """Merging a newer artifact of an existing kind replaces the old one."""
        from packages.pipeline_services.job_tick_service import _merge_artifacts

        existing = [
            ArtifactPointer(
                kind="final_video",
                relative_path="final.mp4",
                size_bytes=100,
            ),
        ]
        new = [
            ArtifactPointer(
                kind="final_video",
                relative_path="final.mp4",
                size_bytes=200,
            ),
        ]
        merged = _merge_artifacts(existing, new)
        assert len(merged) == 1
        assert merged[0].size_bytes == 200

    def test_appends_new_kind(self) -> None:
        """New artifact kinds are appended while preserving existing order."""
        from packages.pipeline_services.job_tick_service import _merge_artifacts

        existing = [
            ArtifactPointer(kind="script", relative_path="script.txt"),
        ]
        new = [
            ArtifactPointer(kind="final_video", relative_path="final.mp4"),
        ]
        merged = _merge_artifacts(existing, new)
        assert [a.kind for a in merged] == ["script", "final_video"]


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
        """tts_review is in both REVIEW and HANDLED sets; final_review is only in REVIEW."""
        assert "tts_review" in REVIEW_PHASES
        assert "tts_review" in HANDLED_PHASES
        assert "final_review" in REVIEW_PHASES
        assert "final_review" not in HANDLED_PHASES

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


# ---------------------------------------------------------------------------
# _build_phase_context — language forwarding
# ---------------------------------------------------------------------------


class TestBuildPhaseContextLanguage:
    """_build_phase_context forwards record.language to PhaseContext.options."""

    def test_forwards_cantonese_language(self) -> None:
        """语言为 cantonese 时 PhaseContext.options 中存在 language."""
        record = JobRecord(
            language="cantonese",
            job_id="test-job",
            project_id="proj-001",
            product="test",
            phase="queued",
            review_status="none",
        )
        svc = JobTickService(
            orchestrator=Mock(spec=PhaseOrchestrator),
            repo=Mock(spec=FileStoreRepository),
        )
        ctx = svc._build_phase_context(
            record=record,
            project_id="proj-001",
            job_id="test-job",
            product="test",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )
        assert ctx.options.get("language") == "cantonese"

    def test_forwards_mandarin_language(self) -> None:
        """语言为 mandarin 时也同样转发。"""
        record = JobRecord(
            language="mandarin",
            job_id="test-job",
            project_id="proj-001",
            product="test",
            phase="queued",
            review_status="none",
        )
        svc = JobTickService(
            orchestrator=Mock(spec=PhaseOrchestrator),
            repo=Mock(spec=FileStoreRepository),
        )
        ctx = svc._build_phase_context(
            record=record,
            project_id="proj-001",
            job_id="test-job",
            product="test",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )
        assert ctx.options.get("language") == "mandarin"


# ---------------------------------------------------------------------------
# JobTickService integration tests
# ---------------------------------------------------------------------------
