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
from packages.domain_core.phase_execution import (
    PhaseExecutionFailure,
    PhaseExecutionSuccess,
)
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import (
    HANDLED_PHASES,
    JobTickService,
    PhaseExecutionError,
    TickAction,
    _compute_transition,
    _transition_after_artifacts,
)
from packages.pipeline_services.sentence_tts_service import SentenceTiming
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
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
    mode: str = "generate",
    manual_script: str = "",
    execution: PhaseExecutionState | None = None,
    artifacts: list[ArtifactPointer] | None = None,
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
        manual_script=manual_script,
        execution=execution if execution is not None else PhaseExecutionState(),
        artifacts=artifacts if artifacts is not None else [],
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

    def test_auto_approve_no_handler_final_review(self) -> None:
        """final_review is no longer a handled phase → auto-approve just advances."""
        action = _compute_transition(
            make_record(phase="final_review", auto_approve=True),
            (),
        )
        assert action.run_handler is False
        assert action.new_phase == _next("final_review")  # "completed"
        assert action.new_review_status == "approved"

    def test_auto_approve_with_approved_does_not_reapprove(self) -> None:
        """Already-approved reviews should advance, not re-auto-approve."""
        action = _compute_transition(
            make_record(
                phase="script_review", review_status="approved", auto_approve=True
            ),
            (),
        )
        # The "approved" check precedes the auto_approve check
        assert action.new_phase == _next("script_review")
        assert action.new_review_status == "none"
        assert action.run_handler is False

    def test_auto_approve_with_pending_does_not_reapprove(self) -> None:
        """Already-pending reviews should wait, not auto-approve."""
        action = _compute_transition(
            make_record(
                phase="script_review", review_status="pending", auto_approve=True
            ),
            (),
        )
        assert action.run_handler is False
        assert action.new_phase is None

    def test_auto_approve_with_skip_subtitle_chains_past_subtitle(self) -> None:
        """auto_approve + skip_subtitle should skip over subtitle_generating."""
        # tts_review → normally → subtitle_generating, but with skip_subtitle
        # should go directly to asset_retrieving
        action = _compute_transition(
            make_record(phase="tts_review", auto_approve=True, skip_subtitle=True),
            (),
        )
        assert action.new_phase == "asset_retrieving"  # skips subtitle_generating
        assert action.new_review_status == "approved"

    def test_auto_approve_skip_subtitle_no_handler(self) -> None:
        """auto_approve + skip_subtitle on a no-handler review still chains."""
        # asset_review has no handler, now advances to montage_assembling
        # (montage_assembling is now between asset_review and video_rendering).
        action = _compute_transition(
            make_record(phase="asset_review", auto_approve=True, skip_subtitle=True),
            (),
        )
        assert action.new_phase == "montage_assembling"
        assert action.new_review_status == "approved"

    def test_auto_approve_no_skip_subtitle_goes_to_subtitle(self) -> None:
        """Without skip_subtitle, auto_approve should still go to subtitle."""
        action = _compute_transition(
            make_record(phase="tts_review", auto_approve=True),
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
        [
            p
            for p in HANDLED_PHASES
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
# JobTickService integration tests
# ---------------------------------------------------------------------------


class TestJobTickService:
    """Tests for JobTickService.tick()."""

    def test_tick_runs_handler_and_advances(self) -> None:
        """tick() should run the handler and advance phase."""
        record = make_record(phase="queued")
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.run_phase.return_value = [
            ArtifactPointer(kind="script", relative_path="script.txt")
        ]

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action in ("advanced", "completed")
        mock_orch.run_phase.assert_called_once()
        assert mock_repo.save_job.call_count >= 1

    def test_tick_skips_terminal_phase(self) -> None:
        """Terminal jobs should be skipped."""
        record = make_record(phase="completed")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        svc = JobTickService(orchestrator=Mock(spec=PhaseOrchestrator), repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )
        assert summary.action == "skipped"
        mock_repo.save_job.assert_not_called()

    def test_tick_wraps_orchestrator_error(self) -> None:
        """Orchestrator failure should raise PhaseExecutionError."""
        record = make_record(phase="script_generating")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.run_phase.side_effect = RuntimeError("API failure")

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        with pytest.raises(PhaseExecutionError) as exc:
            svc.tick(
                "proj-001",
                "test-job",
                "羊肚菌",
                root_dir=Path("/tmp"),
                project_dir=Path("/tmp/proj"),
            )
        assert exc.value.job_id == "test-job"
        assert exc.value.phase == "script_generating"

    def test_deterministic_media_failure_stops_immediately(self) -> None:
        record = make_record(phase="video_rendering", mode="import")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="VIDEO_SOURCE_MISSING",
                message="No usable video source is available.",
                retryable=False,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "video_rendering"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 1
        assert saved.execution.error.code == "VIDEO_SOURCE_MISSING"

    def test_transient_failure_enters_retrying_first_attempt(self) -> None:
        """First retryable failure → retrying state."""
        record = make_record(phase="video_rendering", mode="import")
        latest: list[JobRecord] = [record]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        mock_repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)
        mock_orch = Mock(spec=PhaseOrchestrator)
        # Always fail — the first failure enters retrying, chain stops.
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="MEDIA_PROCESSING_TIMEOUT",
                message="Media processing timed out.",
                retryable=True,
            )
        )

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo, sleep_fn=None)
        svc.tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # After 3 retries (total 4 attempts with the initial), terminal.
        saved = mock_repo.save_job.call_args_list[-1][0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "video_rendering"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 4  # max_attempts=3 retries + 1
        assert saved.execution.max_attempts == 3

    def test_retryable_failure_exhausts_after_max_retries(self) -> None:
        """When max_attempts retries are exhausted, the failure is terminal."""
        record = make_record(phase="video_rendering", mode="import")
        record.execution = record.execution.model_copy(
            update={"status": "retrying", "current_attempt": 3}
        )
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="MEDIA_PROCESSING_TIMEOUT",
                message="Media processing timed out.",
                retryable=True,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "video_rendering"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 4
        assert saved.execution.max_attempts == 3

    def test_structured_success_advances_and_preserves_upstream_artifacts(self) -> None:
        upstream = ArtifactPointer(kind="scene_segment", relative_path="scene.mp4")
        record = make_record(phase="video_rendering", mode="import")
        record.artifacts = [upstream]
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        output = ArtifactPointer(kind="video_base", relative_path="base.mp4")
        mock_orch.execute_phase.return_value = PhaseExecutionSuccess(artifacts=[output])

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args_list[-1][0][1]
        # Chain advances: video_rendering → final_rendering → final_review (gate).
        assert saved.phase in ("final_rendering", "final_review")
        artifact_kinds = {artifact.kind for artifact in saved.artifacts}
        assert "scene_segment" in artifact_kinds
        assert "video_base" in artifact_kinds
        assert saved.execution.status == "succeeded"

    def test_empty_structured_success_becomes_bounded_internal_failure(self) -> None:
        record = make_record(phase="video_rendering", mode="import")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionSuccess(artifacts=[])

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "video_rendering"
        assert saved.execution.error.code == "INTERNAL_EMPTY_RESULT"

    def test_failed_job_is_terminal_and_does_not_repeat_media_handler(self) -> None:
        record = make_record(phase="failed", mode="import")
        record.failed_phase = "video_rendering"
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        mock_orch.execute_phase.assert_not_called()
        mock_repo.save_job.assert_not_called()

    def test_tick_injects_manual_script_for_generate_mode(self) -> None:
        """Generate mode 下 tick() 自动将 JobRecord.manual_script 注入 options。"""
        record = make_record(
            phase="queued",
            mode="generate",
            manual_script="手动文案走 generate 路径",
        )
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.run_phase.return_value = [
            ArtifactPointer(kind="script", relative_path="script.txt")
        ]

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action in ("advanced", "completed")
        ctx_arg = mock_orch.run_phase.call_args[0][1]
        assert ctx_arg.options["manual_script"] == "手动文案走 generate 路径"

    def test_generate_manual_script_advances_to_script_review_not_scene_assembling(
        self,
    ) -> None:
        """Generate + manual_script 从 queued 进入 script_generating，产物出来后到 script_review，不去 scene_assembling。"""
        record = make_record(
            phase="queued",
            mode="generate",
            manual_script="手动文案",
        )
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.run_phase.return_value = [
            ArtifactPointer(kind="script", relative_path="script.txt")
        ]

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.to_phase == "script_review"
        mock_orch.run_phase.assert_called_once()
        assert mock_orch.run_phase.call_args[0][0] == "script_generating"

    def test_generate_manual_script_full_chain(
        self,
    ) -> None:
        """Generate + manual_script one tick chains through the full pipeline."""
        record = make_record(
            phase="queued",
            mode="generate",
            manual_script="手动文案",
            auto_approve=True,
            skip_subtitle=True,
        )
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.run_phase.return_value = [
            ArtifactPointer(kind="artifact", relative_path="out"),
        ]
        mock_orch.execute_phase.return_value = PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")],
        )

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # With auto_approve + skip_subtitle, one tick chains all the way to
        # completed (terminal).
        assert summary.action == "completed"
        assert summary.to_phase == "completed"

    def test_retrying_state_preserves_retryable_error(self) -> None:
        """重试耗尽后，retryable 失败的 error 在终态中仍被保留。"""
        record = make_record(phase="video_rendering", mode="import")
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="MEDIA_PROCESSING_TIMEOUT",
                message="Media processing timed out.",
                retryable=True,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args_list[-1][0][1]
        assert saved.execution.status == "failed"
        assert saved.execution.error is not None
        assert saved.execution.error.code == "MEDIA_PROCESSING_TIMEOUT"

    def test_scene_retry_with_existing_tts_audio_does_not_rerun_tts(self) -> None:
        """scene_assembling 重试时已有 tts_audio 产物 → 不再并行重跑 TTS。"""
        record = make_record(phase="scene_assembling", mode="import")
        record.artifacts = [
            ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")
        ]
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="scene_segment", relative_path="scene.mp4")]
        )
        # Chain continues to unstructured phases (asset_retrieving) that use
        # run_phase; return an empty artifact list so the chain proceeds.
        mock_orch.run_phase.return_value = []

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        mock_orch.execute_phases_parallel.assert_not_called()
        execute_phase_names = [
            call[0][0] for call in mock_orch.execute_phase.call_args_list
        ]
        assert "scene_assembling" in execute_phase_names
        assert "tts_generating" not in execute_phase_names
        saved = mock_repo.save_job.call_args_list[-1][0][1]
        # Chain advances: scene → subtitle → montage → video → final → final_review
        assert saved.phase != "scene_assembling"
        artifact_kinds = {a.kind for a in saved.artifacts}
        assert "tts_audio" in artifact_kinds
        assert "scene_segment" in artifact_kinds

    def test_parallel_primary_failure_keeps_parallel_success_artifacts(self) -> None:
        """并行主 phase 失败时，同 tick 成功的 tts_audio 指针不得被丢弃。"""
        record = make_record(phase="scene_assembling", mode="import")
        latest: list[JobRecord] = [record]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        mock_repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phases_parallel.return_value = {
            "scene_assembling": PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="MEDIA_PROCESSING_TIMEOUT",
                    message="Scene assembly timed out.",
                    retryable=True,
                )
            ),
            "tts_generating": PhaseExecutionSuccess(
                artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")]
            ),
        }

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args_list[-1][0][1]
        # Handler always fails → retries exhaust → terminal failed.
        # But tts_audio from the parallel success is preserved.
        assert saved.phase == "failed"
        assert saved.execution.status == "failed"
        assert [a.kind for a in saved.artifacts] == ["tts_audio"]

    def test_parallel_tts_failure_is_attributed_to_tts_phase(self) -> None:
        """并行 TTS 失败不得"成功"推进，失败须归因到 tts_generating。"""
        record = make_record(phase="scene_assembling", mode="import")
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phases_parallel.return_value = {
            "scene_assembling": PhaseExecutionSuccess(
                artifacts=[
                    ArtifactPointer(kind="scene_segment", relative_path="scene.mp4")
                ]
            ),
            "tts_generating": PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="INTERNAL_EMPTY_RESULT",
                    message="tts_generating reported success without an artifact.",
                    retryable=False,
                )
            ),
        }

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "tts_generating"
        assert saved.execution.error.code == "INTERNAL_EMPTY_RESULT"
        assert [a.kind for a in saved.artifacts] == ["scene_segment"]


# ---------------------------------------------------------------------------
# JobTickService.advance_after_report
# ---------------------------------------------------------------------------


class TestAdvanceAfterReport:
    def test_advances_from_non_review_phase(self) -> None:
        """Worker report on a non-review phase advances to next phase."""
        record = make_record(phase="tts_generating")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record

        svc = JobTickService(orchestrator=Mock(spec=PhaseOrchestrator), repo=mock_repo)
        summary = svc.advance_after_report(
            "proj-001",
            "test-job",
            [{"relative_path": "audio.mp3", "size_bytes": 1024}],
        )
        assert summary.action == "advanced"
        assert summary.to_phase == "tts_review"  # advances to review
        mock_repo.save_job.assert_called_once()

    def test_sets_review_pending_when_advancing_to_review(self) -> None:
        """Advancing from a gate phase into a review sets review_status=pending."""
        record = make_record(phase="tts_generating")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record

        svc = JobTickService(orchestrator=Mock(spec=PhaseOrchestrator), repo=mock_repo)
        svc.advance_after_report(
            "proj-001",
            "test-job",
            [{"relative_path": "audio.mp3", "size_bytes": 2048}],
        )
        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "tts_review"
        assert saved.review_status == "pending"

    def test_skips_when_already_at_terminal(self) -> None:
        """Report on a completed job should skip."""
        record = make_record(phase="completed")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record

        svc = JobTickService(orchestrator=Mock(spec=PhaseOrchestrator), repo=mock_repo)
        summary = svc.advance_after_report("proj-001", "test-job", [])
        assert summary.action == "skipped"

    def test_merges_artifacts_from_manifest(self) -> None:
        """Artifacts from worker manifest should be merged into the record."""
        record = make_record(phase="video_rendering")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record

        svc = JobTickService(orchestrator=Mock(spec=PhaseOrchestrator), repo=mock_repo)
        svc.advance_after_report(
            "proj-001",
            "test-job",
            [{"relative_path": "final_video.mp4", "size_bytes": 50000}],
        )
        saved = mock_repo.save_job.call_args[0][1]
        assert len(saved.artifacts) == 1
        assert saved.artifacts[0].kind == "final_video"


# ---------------------------------------------------------------------------
# 11. Manual script consistency regression test (#188)
# ---------------------------------------------------------------------------


class TestManualScriptConsistency:
    """Regression: manual_script text preserved through _run_script → _run_tts → _run_subtitle."""

    def test_manual_script_preserved_through_pipeline(self, tmp_path: Path) -> None:
        manual_text = "这是用户提交的口播文案。用于短视频配音。确保完全一致。"
        job_id = "test-job-consistency"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"

        # PhaseOrchestrator with mocked external deps
        mock_config = Mock()
        mock_config.get_tts_config.return_value = {
            "model": "test-model",
            "voice": "test-voice",
        }
        orch = PhaseOrchestrator(
            subtitle_svc=Mock(),
            video_svc=Mock(),
            config_reader=mock_config,
        )

        # Mock TTS provider to avoid real API calls
        mock_tts = Mock()
        mock_tts.synthesize.return_value = b"fake_audio_data"
        orch._build_tts_provider = Mock(return_value=mock_tts)

        ctx = PhaseContext(
            job_id=job_id,
            project_dir=project_dir,
            root_dir=root_dir,
            product="test_product",
            options={"manual_script": manual_text},
        )

        # --- seam A: _run_script writes exact text to disk ---
        orch._run_script(ctx)
        job_dir = project_dir / "runtime" / "jobs" / job_id
        txt_path = job_dir / "口播文案.txt"
        assert txt_path.read_text(encoding="utf-8") == manual_text

        # --- seam B: _discover_script reads it back ---
        discovered = PhaseOrchestrator._discover_script(job_dir)
        assert discovered == manual_text

        # --- seam C: _run_tts passes the exact script text to the SentenceTTSService ---
        def _fake_synthesize_script(
            script_text: str, output_path: Path
        ) -> list[SentenceTiming]:
            output_path.write_bytes(b"fake_audio_data")
            return [
                SentenceTiming(
                    index=0,
                    text=script_text,
                    start_seconds=0.0,
                    end_seconds=1.0,
                    model="test-model",
                    voice="test-voice",
                )
            ]

        fake_service = Mock()
        fake_service.synthesize_script.side_effect = _fake_synthesize_script
        orch._create_sentence_tts_service = Mock(return_value=fake_service)

        orch._run_tts(ctx)
        orch._create_sentence_tts_service.assert_called_once()
        fake_service.synthesize_script.assert_called_once()
        tts_script_text = fake_service.synthesize_script.call_args[0][0]
        assert tts_script_text == manual_text

        # --- seam D: _run_subtitle passes exact text to subtitle service ---
        orch._run_subtitle(ctx)
        orch._subtitle_svc.build_srt.assert_called_once()
        subtitle_text = orch._subtitle_svc.build_srt.call_args[0][2]
        assert subtitle_text == manual_text


# ---------------------------------------------------------------------------
# 12. Import-mode scene input validation
# ---------------------------------------------------------------------------


class TestImportSceneInput:
    """Import jobs require valid scene folders and fail non-retryably."""

    def test_import_job_with_empty_scene_folder_ids_goes_to_migration_required(
        self,
    ) -> None:
        """An import job queued without selected scene folders is paused for migration."""
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = []
        action = _compute_transition(record, ())
        assert action.new_phase == "migration_required"
        assert action.run_handler is False

    def test_import_job_with_scene_folders_routes_to_scene_assembling(
        self,
    ) -> None:
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = ["scenes/one"]
        action = _compute_transition(record, ())
        assert action.new_phase == "scene_assembling"
        assert action.run_handler is False

    def test_scene_assembling_failure_on_missing_input_is_not_retryable(
        self,
    ) -> None:
        record = make_record(phase="scene_assembling", mode="import")
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phases_parallel.return_value = {
            "scene_assembling": PhaseExecutionFailure(
                error=ExecutionFailure(
                    code="SCENE_INPUT_MISSING",
                    message="No scene folders are configured for this Job.",
                    retryable=False,
                )
            ),
            "tts_generating": PhaseExecutionSuccess(artifacts=[]),
        }

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "scene_assembling"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 1
        assert saved.execution.error.code == "SCENE_INPUT_MISSING"

    def test_migration_required_is_terminal_for_tick(self) -> None:
        record = make_record(phase="migration_required", mode="import")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        svc = JobTickService(Mock(spec=PhaseOrchestrator), repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )
        assert summary.action == "skipped"
        mock_repo.save_job.assert_not_called()

    def test_queued_generate_job_does_not_require_scene_folders(self) -> None:
        record = make_record(phase="queued", mode="generate")
        record.scene_folder_ids = []
        action = _compute_transition(record, ())
        assert action.new_phase is None
        assert action.handler_phase == "script_generating"


class TestImportSceneFolderFallback:
    """#275: tick() fallback scene_folder_ids from scene config for import mode."""

    def test_tick_import_empty_folders_with_scene_config_routes_to_scene_assembling(
        self,
    ) -> None:
        """import + empty scene_folder_ids + product scene config → scene_assembling."""
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = []
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_config = Mock()
        mock_config.get_scene_config.return_value = {
            "folders": [
                {"path": "scenes/snack", "label": "零食"},
                {"path": "scenes/drink", "label": "饮品"},
            ],
            "transition_duration_ms": 500,
        }

        svc = JobTickService(
            orchestrator=mock_orch, repo=mock_repo, config_reader=mock_config
        )
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action == "advanced"
        assert summary.to_phase == "scene_assembling"
        saved = mock_repo.save_job.call_args[0][1]
        assert saved.scene_folder_ids == ["scenes/snack", "scenes/drink"]

    def test_tick_import_empty_folders_no_scene_config_goes_to_migration_required(
        self,
    ) -> None:
        """import + empty scene_folder_ids + no product scene config → migration_required."""
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = []
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_config = Mock()
        mock_config.get_scene_config.return_value = {"folders": []}

        svc = JobTickService(
            orchestrator=Mock(spec=PhaseOrchestrator),
            repo=mock_repo,
            config_reader=mock_config,
        )
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action == "advanced"
        assert summary.to_phase == "migration_required"

    def test_tick_import_with_existing_folders_unaffected(self) -> None:
        """import + existing scene_folder_ids → behavior unchanged, no config fallback."""
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = ["scenes/existing"]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_config = Mock()

        svc = JobTickService(
            orchestrator=Mock(spec=PhaseOrchestrator),
            repo=mock_repo,
            config_reader=mock_config,
        )
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action == "advanced"
        assert summary.to_phase == "scene_assembling"
        # config_reader should NOT have been called since folders already exist
        mock_config.get_scene_config.assert_not_called()

    def test_tick_generate_job_unaffected_by_scene_config(self) -> None:
        """generate mode → unaffected by scene config fallback."""
        record = make_record(phase="queued", mode="generate")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.run_phase.return_value = [
            ArtifactPointer(kind="script", relative_path="script.txt")
        ]

        svc = JobTickService(
            orchestrator=mock_orch, repo=mock_repo, config_reader=Mock()
        )
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action in ("advanced", "completed")


# ---------------------------------------------------------------------------
# 13. TTS failure semantics (#253)
# ---------------------------------------------------------------------------


class TestTTSFailureSemantics:
    """TTS synthesis failures keep job at tts_generating, never advance to tts_review."""

    def test_tts_retryable_failure_stays_in_phase(self) -> None:
        """retryable TTS failure → retried inline, then advances to tts_review."""
        record = make_record(phase="tts_generating", mode="generate")
        latest: list[JobRecord] = [record]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        mock_repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)

        call_count = [0]
        mock_orch = Mock(spec=PhaseOrchestrator)

        def _execute_side(phase, ctx):
            call_count[0] += 1
            if call_count[0] == 1:
                return PhaseExecutionFailure(
                    error=ExecutionFailure(
                        code="TTS_SYNTHESIS_FAILED",
                        message="TTS synthesis failed: network error",
                        retryable=True,
                    )
                )
            return PhaseExecutionSuccess(
                artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")]
            )

        mock_orch.execute_phase.side_effect = _execute_side

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # After retry succeeds, chain advances past tts_review (auto_approve=False
        # stops at the review gate).
        saved = mock_repo.save_job.call_args_list[-1][0][1]
        assert saved.phase == "tts_review"
        assert saved.review_status == "pending"
        assert saved.execution.status == "succeeded"
        # Handler was called twice: first failure, then retry success.
        assert call_count[0] == 2

    def test_tts_non_retryable_failure_marks_failed_immediately(self) -> None:
        """Non-retryable TTS failure → immediate terminal failed."""
        record = make_record(phase="tts_generating", mode="generate")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_PROVIDER_REJECTED",
                message="TTS 服务拒绝请求（鉴权失败或参数无效）",
                retryable=False,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "tts_generating"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 1
        assert saved.execution.error is not None
        assert saved.execution.error.code == "TTS_PROVIDER_REJECTED"
        assert saved.execution.error.retryable is False

    def test_tts_retryable_failure_exhausts_all_retries_then_fails(self) -> None:
        """When the handler always fails, all max_attempts retries exhaust → terminal."""
        record = make_record(phase="tts_generating", mode="generate")
        latest: list[JobRecord] = [record]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        mock_repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_QUOTA_EXCEEDED",
                message="TTS 配额超限",
                retryable=True,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args_list[-1][0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "tts_generating"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 4  # max_attempts=3 retries + 1 = 4

    def test_tts_retryable_failure_with_prior_retries_goes_terminal(self) -> None:
        """With 3 prior retries, the 4th failure is terminal immediately."""
        record = make_record(phase="tts_generating", mode="generate")
        record.execution = record.execution.model_copy(
            update={"status": "retrying", "current_attempt": 3, "max_attempts": 3}
        )
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_QUOTA_EXCEEDED",
                message="TTS 配额超限",
                retryable=True,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "tts_generating"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 4

    def test_tts_failure_preserves_upstream_script_artifact(self) -> None:
        """TTS failure preserves script artifact — only tts_audio is absent."""
        script_artifact = ArtifactPointer(kind="script", relative_path="script.txt")
        record = make_record(phase="tts_generating", mode="generate")
        record.artifacts = [script_artifact]
        latest: list[JobRecord] = [record]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        mock_repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_SYNTHESIS_FAILED",
                message="TTS synthesis failed",
                retryable=True,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args_list[-1][0][1]
        assert len(saved.artifacts) == 1
        assert saved.artifacts[0].kind == "script"

    def test_tts_no_artifacts_stays_in_phase_not_auto_advance(self) -> None:
        """tts_generating with no artifacts (defensive) must NOT auto-advance."""
        action = _transition_after_artifacts(
            make_record(phase="tts_generating"),
            (),
        )
        assert action.new_phase is None
        assert "staying" in action.message.lower()

    def test_tts_success_advances_to_review(self) -> None:
        """Successful TTS with artifacts → advance to tts_review."""
        record = make_record(phase="tts_generating", mode="generate")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")],
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "tts_review"
        assert saved.execution.status == "succeeded"
        assert saved.review_status == "pending"


class TestTTSRetriesExhaustedNonRetryable:
    """SentenceTTSService exhausted → phase-level retry NOT triggered (#266)."""

    def test_tts_retries_exhausted_is_not_retryable(self) -> None:
        """When TTSRetriesExhaustedError is raised, the phase failure is terminal."""
        record = make_record(phase="tts_generating", mode="generate")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        # Simulate execute_phase propagating the sentinel as a structured failure.
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_RETRIES_EXHAUSTED",
                message="TTS 单句重试已耗尽: ...",
                retryable=False,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "tts_generating"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 1  # no retry


class TestRetryReload:
    """After a retryable failure and backoff, the record is reloaded from disk."""

    def test_reload_after_backoff_observes_external_cancel(self) -> None:
        """If the job is cancelled during backoff, the retry loop stops."""
        record = make_record(phase="video_rendering", mode="import")
        cancelled = make_record(phase="cancelled", mode="import")
        load_sequence: list[JobRecord] = [record, cancelled]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.side_effect = lambda p, j: load_sequence.pop(0)
        mock_repo.save_job.return_value = None
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="MEDIA_PROCESSING_TIMEOUT",
                message="Media processing timed out.",
                retryable=True,
            )
        )

        slept: list[float] = []
        svc = JobTickService(
            orchestrator=mock_orch, repo=mock_repo, sleep_fn=lambda s: slept.append(s)
        )
        summary = svc.tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # Handler should NOT have been retried — the reload saw cancelled.
        assert mock_orch.execute_phase.call_count == 1, (
            f"Expected 1 execute_phase call, got {mock_orch.execute_phase.call_count}"
        )
        assert "cancelled" in summary.message.lower()

    def test_reload_after_backoff_rebuilds_context(self) -> None:
        """External voice change during backoff is visible in the rebuilt context."""
        record = make_record(phase="tts_generating", mode="generate")
        record.tts_voice = "Mia"
        latest: list[JobRecord] = [record]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        mock_repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)

        call_contexts: list[str] = []
        mock_orch = Mock(spec=PhaseOrchestrator)
        # Intercept save to inject voice change after the retrying record is
        # persisted, so the reload observes the edit.
        orig_save = mock_repo.save_job.side_effect

        def _save_wrapper(p, r):
            orig_save(p, r)  # persist the retrying state
            # Simulate user switching voice in the UI between attempts.
            rec = latest[0].model_copy()
            rec.tts_voice = "Dean"
            latest[0] = rec

        mock_repo.save_job.side_effect = _save_wrapper

        def _execute_side_effect(phase, ctx):
            call_contexts.append(ctx.options.get("tts_voice", ""))
            if len(call_contexts) == 1:
                return PhaseExecutionFailure(
                    error=ExecutionFailure(
                        code="TTS_SYNTHESIS_FAILED",
                        message="TTS synthesis failed.",
                        retryable=True,
                    )
                )
            return PhaseExecutionSuccess(
                artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")]
            )

        mock_orch.execute_phase.side_effect = _execute_side_effect
        mock_orch.run_phase.return_value = [
            ArtifactPointer(kind="artifact", relative_path="out")
        ]

        slept: list[float] = []
        JobTickService(
            orchestrator=mock_orch, repo=mock_repo, sleep_fn=lambda s: slept.append(s)
        ).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # First attempt: Mia, Second attempt (after reload): Dean.
        assert call_contexts == ["Mia", "Dean"], (
            f"Expected ['Mia', 'Dean'], got {call_contexts}"
        )


# 13. Auto-approve asset_review integrity checks + snapshot (#254)
# ---------------------------------------------------------------------------


class TestAutoApproveAssetReviewIntegrity:
    """Auto-approval of asset_review must perform the same checks as manual approval."""

    def test_auto_approve_with_unresolved_does_not_advance(
        self, tmp_path: Path
    ) -> None:
        """Auto-approve should NOT advance if selected_clips.json has unresolved entries."""
        import json as _json

        job_id = "test-job-auto"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Write selected_clips with an unresolved entry
        clips = [
            {
                "sentence": "已匹配句。",
                "sentence_index": 0,
                "category": "intro",
                "file_path": "/data/clip1.mp4",
                "asset_id": "a1",
                "duration_seconds": 5.0,
                "method": "llm_match",
                "visual_type": "clip",
            },
            {
                "sentence": "未解决句。",
                "sentence_index": 1,
                "category": "",
                "file_path": "",
                "asset_id": "",
                "duration_seconds": 0.0,
                "method": "",
                "visual_type": "unresolved",
            },
        ]
        (job_dir / "selected_clips.json").write_text(
            _json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Create job record with auto_approve=True, phase=asset_review, review_status="none"
        record = make_record(
            phase="asset_review", auto_approve=True, review_status="none"
        )
        record.job_id = job_id

        # Use real FileStoreRepository so the tick service can read from disk
        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        # Should NOT have advanced — unresolved clips block auto-approval
        saved = repo.load_job("proj-001", job_id)
        assert saved.phase == "asset_review", (
            f"Expected asset_review, got {saved.phase}"
        )

    def test_auto_approve_all_blank_proceeds(self, tmp_path: Path) -> None:
        """Auto-approve should proceed for all-blank clips (force=true is implicit)."""
        import json as _json

        job_id = "test-job-blank"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        clips = [
            {
                "sentence": "全空白一。",
                "sentence_index": 0,
                "visual_type": "blank",
                "file_path": "",
                "asset_id": "",
            },
            {
                "sentence": "全空白二。",
                "sentence_index": 1,
                "visual_type": "blank",
                "file_path": "",
                "asset_id": "",
            },
        ]
        (job_dir / "selected_clips.json").write_text(
            _json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        record = make_record(
            phase="asset_review", auto_approve=True, review_status="none"
        )
        record.job_id = job_id

        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        saved = repo.load_job("proj-001", job_id)
        # Should have advanced past asset_review (auto_approve proceeds for all-blank)
        assert saved.phase != "asset_review", (
            f"Expected advance past asset_review, got {saved.phase}"
        )
        assert saved.review_status == "approved"

    def test_auto_approve_writes_reviewed_snapshot(self, tmp_path: Path) -> None:
        """Auto-approval writes reviewed_assets.json snapshot."""
        import json as _json

        job_id = "test-job-snapshot"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        clips = [
            {
                "sentence": "第一句。",
                "sentence_index": 0,
                "category": "intro",
                "file_path": "/data/clip1.mp4",
                "asset_id": "a1",
                "duration_seconds": 5.0,
                "method": "llm_match",
                "visual_type": "clip",
            },
        ]
        (job_dir / "selected_clips.json").write_text(
            _json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        record = make_record(
            phase="asset_review", auto_approve=True, review_status="none"
        )
        record.job_id = job_id

        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        # Snapshot must exist
        snapshot_path = job_dir / "reviewed_assets.json"
        assert snapshot_path.exists(), (
            "reviewed_assets.json should be written on auto-approve"
        )
        snapshot = _json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert len(snapshot) == 1
        assert snapshot[0]["visual_type"] == "clip"
        assert snapshot[0]["asset_id"] == "a1"
        assert snapshot[0]["sentence_index"] == 0

    def test_auto_approve_clean_clips_proceeds(self, tmp_path: Path) -> None:
        """Auto-approve with all-clip entries should advance normally."""
        import json as _json

        job_id = "test-job-clean"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        clips = [
            {
                "sentence": "第一句。",
                "sentence_index": 0,
                "category": "intro",
                "file_path": "/data/clip1.mp4",
                "asset_id": "a1",
                "visual_type": "clip",
            },
            {
                "sentence": "第二句。",
                "sentence_index": 1,
                "category": "detail",
                "file_path": "/data/clip2.mp4",
                "asset_id": "a2",
                "visual_type": "clip",
            },
        ]
        (job_dir / "selected_clips.json").write_text(
            _json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        record = make_record(
            phase="asset_review", auto_approve=True, review_status="none"
        )
        record.job_id = job_id

        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        saved = repo.load_job("proj-001", job_id)
        assert saved.phase != "asset_review"
        assert saved.review_status == "approved"


# ---------------------------------------------------------------------------
# montage_assembling failure preserves upstream artifacts (#264)
# ---------------------------------------------------------------------------


class TestMontageAssemblingFailure:
    """montage_assembling failure correctly records failed_phase and preserves
    upstream artifacts (tts_audio, sentence_timings, selected_clips)."""

    def test_non_retryable_failure_sets_failed_phase(self) -> None:
        """Non-retryable montage failure → terminal failed, phase=failed."""
        record = make_record(
            phase="montage_assembling",
            mode="generate",
            artifacts=[
                ArtifactPointer(
                    kind="tts_audio", relative_path="audio.mp3", size_bytes=100
                ),
                ArtifactPointer(
                    kind="sentence_timings",
                    relative_path="sentences.json",
                    size_bytes=80,
                ),
            ],
        )
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="MONTAGE_INPUT_INVALID",
                message="Montage input is invalid: missing clip file",
                retryable=False,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "montage_assembling"
        assert saved.execution.status == "failed"
        assert saved.execution.error is not None
        assert saved.execution.error.code == "MONTAGE_INPUT_INVALID"
        # Upstream artifacts are preserved.
        artifact_kinds = {a.kind for a in saved.artifacts}
        assert "tts_audio" in artifact_kinds
        assert "sentence_timings" in artifact_kinds

    def test_retryable_failure_preserves_artifacts_and_stays_in_phase(self) -> None:
        """Retryable montage failure exhausts retries → terminal, artifacts preserved."""
        record = make_record(
            phase="montage_assembling",
            mode="import",
            artifacts=[
                ArtifactPointer(
                    kind="tts_audio", relative_path="audio.mp3", size_bytes=100
                ),
                ArtifactPointer(
                    kind="selected_clips",
                    relative_path="selected_clips.json",
                    size_bytes=200,
                ),
            ],
        )
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="MEDIA_PROCESSING_TIMEOUT",
                message="montage_assembling media processing timed out.",
                retryable=True,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args_list[-1][0][1]
        # All retries exhausted → terminal failed.
        assert saved.phase == "failed"
        assert saved.failed_phase == "montage_assembling"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 4
        assert saved.execution.error is not None
        assert saved.execution.error.retryable is True
        # Upstream artifacts are preserved.
        artifact_kinds = {a.kind for a in saved.artifacts}
        assert "tts_audio" in artifact_kinds
        assert "selected_clips" in artifact_kinds

    def test_retryable_failure_exhausts_after_max_attempts(self) -> None:
        """When max_attempts retries are exhausted, montage_assembling failure is
        terminal."""
        record = make_record(
            phase="montage_assembling",
            mode="generate",
            execution=PhaseExecutionState(
                status="retrying",
                current_attempt=3,  # 3 retries done → next is attempt 4 → terminal
                max_attempts=3,
            ),
            artifacts=[
                ArtifactPointer(
                    kind="tts_audio", relative_path="audio.mp3", size_bytes=100
                ),
            ],
        )
        latest: list[JobRecord] = [record]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        mock_repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="MEDIA_PROCESSING_FAILED",
                message="montage_assembling media processing failed.",
                retryable=True,
            )
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        saved = mock_repo.save_job.call_args_list[-1][0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "montage_assembling"
        assert saved.execution.status == "failed"
        # Upstream artifacts are preserved even on terminal failure.
        artifact_kinds = {a.kind for a in saved.artifacts}
        assert "tts_audio" in artifact_kinds


# ---------------------------------------------------------------------------
# 14. Chain advancement (Issue #266)
# ---------------------------------------------------------------------------


class TestChainAdvancement:
    """Chain-advancement: a single tick() pass advances through multiple phases."""

    def _make_persistent_repo(self, initial: JobRecord):
        """Return a mock repo whose load_job/save_job track in-memory state."""
        repo = Mock(spec=FileStoreRepository)
        latest: list[JobRecord] = [initial]

        def _load(project_id: str, job_id: str) -> JobRecord:
            return latest[0].model_copy()

        def _save(project_id: str, rec: JobRecord) -> None:
            latest[0] = rec

        repo.load_job.side_effect = _load
        repo.save_job.side_effect = _save
        return repo

    def _make_success_orch(self) -> Mock:
        """Mock orchestrator that always succeeds both run_phase and execute_phase."""
        orch = Mock(spec=PhaseOrchestrator)
        orch.run_phase.return_value = [
            ArtifactPointer(kind="artifact", relative_path="out")
        ]
        orch.execute_phase.return_value = PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="artifact", relative_path="out")]
        )
        return orch

    def test_tick_chains_multiple_phases_until_review_gate(self) -> None:
        """Generate-mode queued job advances through script_generating and
        stops at script_review (first review gate without auto_approve)."""
        record = make_record(phase="queued", mode="generate", auto_approve=False)
        repo = self._make_persistent_repo(record)
        orch = self._make_success_orch()

        svc = JobTickService(orchestrator=orch, repo=repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # Chain advanced queued → script_generating → script_review, then stopped.
        assert summary.to_phase == "script_review"
        assert summary.action == "advanced"
        # script_generating handler should have been called exactly once.
        run_phase_calls = [
            c for c in orch.run_phase.call_args_list if c[0][0] == "script_generating"
        ]
        assert len(run_phase_calls) == 1

    def test_tick_chains_past_auto_approve_review_gate(self) -> None:
        """auto_approve=True chains through review gates instead of stopping."""
        record = make_record(phase="queued", mode="generate", auto_approve=True)
        repo = self._make_persistent_repo(record)
        orch = self._make_success_orch()

        svc = JobTickService(orchestrator=orch, repo=repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # With auto_approve + all-success orchestrator, the chain should run
        # through the entire pipeline and reach completed (a terminal phase).
        handler_phases: set[str] = set()
        for call in orch.run_phase.call_args_list:
            handler_phases.add(call[0][0])
        for call in orch.execute_phase.call_args_list:
            handler_phases.add(call[0][0])

        # Must have run multiple handlers (script_generating, tts_generating,
        # subtitle_generating, asset_retrieving, montage_assembling,
        # video_rendering, final_rendering — at least 5).
        assert len(handler_phases) >= 5, (
            f"Expected >= 5 handler phases, got {len(handler_phases)}: {handler_phases}"
        )
        # Should have reached a terminal phase (completed).
        assert summary.to_phase == "completed"
        assert summary.action == "completed"

    @pytest.mark.parametrize(
        "terminal_phase", ["completed", "failed", "cancelled", "paused"]
    )
    def test_tick_stops_at_terminal_phase(self, terminal_phase: str) -> None:
        """Chain stops immediately when the job is already in a terminal phase."""
        record = make_record(phase=terminal_phase, mode="generate")
        repo = self._make_persistent_repo(record)
        orch = Mock(spec=PhaseOrchestrator)

        svc = JobTickService(orchestrator=orch, repo=repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action == "skipped"
        orch.run_phase.assert_not_called()
        orch.execute_phase.assert_not_called()

    def test_tick_reloads_record_each_step(self) -> None:
        """External edit (cancel) written to disk between chain steps is observed
        on reload and stops the chain."""
        record_queued = make_record(phase="queued", mode="generate", auto_approve=True)
        record_cancelled = make_record(phase="cancelled", mode="generate")

        repo = Mock(spec=FileStoreRepository)
        repo.load_job.side_effect = [record_queued, record_cancelled]
        repo.save_job.return_value = None

        orch = self._make_success_orch()

        svc = JobTickService(orchestrator=orch, repo=repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # First iteration: queued → handler runs, advances past script_review
        # (auto_approve lets it through). Second iteration: reloads →
        # cancelled → terminal → stops, returning last_summary from step 1.
        assert repo.load_job.call_count >= 2, (
            f"Expected >= 2 load_job calls, got {repo.load_job.call_count}"
        )
        # The chain stopped because of the reloaded cancelled state.
        assert summary.to_phase != "completed"


# ---------------------------------------------------------------------------
# 15. Inline retry with backoff (Issue #266)
# ---------------------------------------------------------------------------


class TestInlineRetry:
    """Inline retry: transient failures retried with exponential backoff."""

    def test_tick_retries_transient_failure_with_backoff(self) -> None:
        """First attempt fails retryably, second succeeds inside the retry loop
        — sleep_fn called with correct backoff time."""
        record = make_record(phase="video_rendering", mode="import")
        # Use persistent repo so chain reloads see the updated record.
        latest: list[JobRecord] = [record]
        repo = Mock(spec=FileStoreRepository)
        repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)

        orch = Mock(spec=PhaseOrchestrator)
        orch.run_phase.return_value = [
            ArtifactPointer(kind="artifact", relative_path="out")
        ]

        execute_call_count = [0]

        def _execute_side_effect(phase, ctx):
            execute_call_count[0] += 1
            if execute_call_count[0] == 1:
                return PhaseExecutionFailure(
                    error=ExecutionFailure(
                        code="MEDIA_PROCESSING_TIMEOUT",
                        message="Media processing timed out.",
                        retryable=True,
                    )
                )
            return PhaseExecutionSuccess(
                artifacts=[ArtifactPointer(kind="video_base", relative_path="base.mp4")]
            )

        orch.execute_phase.side_effect = _execute_side_effect

        slept: list[float] = []
        svc = JobTickService(
            orchestrator=orch, repo=repo, sleep_fn=lambda s: slept.append(s)
        )
        summary = svc.tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # One sleep call with first backoff value (2.0 s).
        assert slept == [2.0], f"Expected [2.0], got {slept}"
        # The first call failed, later calls (retry + chain phases) succeeded.
        assert execute_call_count[0] >= 2, (
            f"Expected >= 2 execute_phase calls, got {execute_call_count[0]}"
        )
        # Job should NOT have failed.
        assert summary.action != "failed"

    def test_tick_fails_after_max_attempts_exhausted(self) -> None:
        """Three retryable failures exhaust max_attempts retries → terminal failed."""
        record = make_record(phase="video_rendering", mode="import")
        latest: list[JobRecord] = [record]
        repo = Mock(spec=FileStoreRepository)
        repo.load_job.side_effect = lambda p, j: latest[0].model_copy()
        repo.save_job.side_effect = lambda p, r: latest.__setitem__(0, r)

        orch = Mock(spec=PhaseOrchestrator)
        orch.run_phase.return_value = [
            ArtifactPointer(kind="artifact", relative_path="out")
        ]
        orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="MEDIA_PROCESSING_TIMEOUT",
                message="Media processing timed out.",
                retryable=True,
            )
        )

        slept: list[float] = []
        svc = JobTickService(
            orchestrator=orch, repo=repo, sleep_fn=lambda s: slept.append(s)
        )
        summary = svc.tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # Attempt 1: sleep(2), Attempt 2: sleep(4), Attempt 3: sleep(8),
        # Attempt 4: terminal (no sleep).
        assert slept == [2.0, 4.0, 8.0], f"Expected [2.0, 4.0, 8.0], got {slept}"
        assert summary.action == "failed"
        assert summary.to_phase == "failed"

        # Verify execution state on the last save.
        saved = repo.save_job.call_args_list[-1][0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "video_rendering"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 4
        assert saved.execution.max_attempts == 3

    def test_tick_non_retryable_error_fails_immediately(self) -> None:
        """Non-retryable error → terminal failed immediately, no backoff."""
        record = make_record(phase="video_rendering", mode="import")
        repo = Mock(spec=FileStoreRepository)
        repo.load_job.return_value = record

        orch = Mock(spec=PhaseOrchestrator)
        orch.run_phase.return_value = [
            ArtifactPointer(kind="artifact", relative_path="out")
        ]
        orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="VIDEO_SOURCE_MISSING",
                message="No usable video source is available.",
                retryable=False,
            )
        )

        slept: list[float] = []
        svc = JobTickService(
            orchestrator=orch, repo=repo, sleep_fn=lambda s: slept.append(s)
        )
        summary = svc.tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # No backoff — went terminal immediately.
        assert slept == [], f"Expected no sleep calls, got {slept}"
        assert summary.action == "failed"
        assert summary.to_phase == "failed"

        saved = repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.execution.status == "failed"
        assert saved.execution.current_attempt == 1
