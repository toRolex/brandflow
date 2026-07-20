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
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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
        mock_repo.save_job.assert_called_once()

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

    @pytest.mark.parametrize(
        ("attempt", "expected_phase", "expected_status"),
        [
            (0, "video_rendering", "retrying"),
            (1, "video_rendering", "retrying"),
            (2, "failed", "failed"),
        ],
    )
    def test_transient_media_failure_is_bounded_at_three_attempts(
        self, attempt: int, expected_phase: str, expected_status: str
    ) -> None:
        record = make_record(phase="video_rendering", mode="import")
        if attempt:
            record.execution = record.execution.model_copy(
                update={"status": "retrying", "current_attempt": attempt}
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
        assert saved.phase == expected_phase
        assert saved.execution.status == expected_status
        assert saved.execution.current_attempt == attempt + 1
        assert saved.execution.max_attempts == 3

    def test_structured_success_advances_and_preserves_upstream_artifacts(self) -> None:
        upstream = ArtifactPointer(kind="scene_segment", relative_path="scene.mp4")
        record = make_record(phase="video_rendering", mode="import")
        record.artifacts = [upstream]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "final_rendering"
        assert [artifact.kind for artifact in saved.artifacts] == [
            "scene_segment",
            "video_base",
        ]
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
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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
        """Generate + manual_script 全程：script_generating → tts_generating → asset_retrieving，不进入 scene_assembling。"""
        record = make_record(
            phase="queued",
            mode="generate",
            manual_script="手动文案",
            auto_approve=True,
            skip_subtitle=True,
        )
        mock_repo = Mock(spec=FileStoreRepository)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.run_phase.return_value = [
            ArtifactPointer(kind="artifact", relative_path="out"),
        ]
        # tts_generating is now a structured phase (#253) — it goes through
        # execute_phase instead of run_phase.
        mock_orch.execute_phase.return_value = PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")],
        )

        # Persist state across ticks: save → load returns the latest saved record
        latest: list[JobRecord] = [record]

        def _load(project_id: str, job_id: str) -> JobRecord:
            return latest[0].model_copy()

        def _save(project_id: str, rec: JobRecord) -> None:
            latest[0] = rec

        mock_repo.load_job.side_effect = _load
        mock_repo.save_job.side_effect = _save

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)

        handler_phases: list[str] = []

        for _ in range(10):
            mock_orch.run_phase.reset_mock()
            mock_orch.run_phase.return_value = [
                ArtifactPointer(kind="artifact", relative_path="out"),
            ]
            mock_orch.execute_phase.reset_mock()
            mock_orch.execute_phase.return_value = PhaseExecutionSuccess(
                artifacts=[
                    ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")
                ],
            )

            summary = svc.tick(
                "proj-001",
                "test-job",
                "羊肚菌",
                root_dir=Path("/tmp"),
                project_dir=Path("/tmp/proj"),
            )

            if mock_orch.run_phase.called:
                handler_phases.append(mock_orch.run_phase.call_args[0][0])
            if mock_orch.execute_phase.called:
                handler_phases.append(mock_orch.execute_phase.call_args[0][0])

            if summary.action in ("completed", "failed"):
                break

        assert len(handler_phases) >= 4
        assert "scene_assembling" not in handler_phases
        assert "script_generating" in handler_phases
        assert "tts_generating" in handler_phases
        assert "asset_retrieving" in handler_phases
        # Verify handler call order
        assert handler_phases.index("script_generating") < handler_phases.index(
            "tts_generating"
        )
        assert handler_phases.index("tts_generating") < handler_phases.index(
            "asset_retrieving"
        )

    def test_retrying_state_preserves_retryable_error(self) -> None:
        """重试期间导致重试的 retryable 失败信息不得丢失。"""
        record = make_record(phase="video_rendering", mode="import")
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
        assert saved.execution.status == "retrying"
        assert saved.execution.error is not None
        assert saved.execution.error.code == "MEDIA_PROCESSING_TIMEOUT"

    def test_scene_retry_with_existing_tts_audio_does_not_rerun_tts(self) -> None:
        """scene_assembling 重试时已有 tts_audio 产物 → 不再并行重跑 TTS。"""
        record = make_record(phase="scene_assembling", mode="import")
        record.artifacts = [
            ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")
        ]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="scene_segment", relative_path="scene.mp4")]
        )

        JobTickService(mock_orch, mock_repo).tick(
            "proj-001",
            "test-job",
            "product",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        mock_orch.execute_phases_parallel.assert_not_called()
        assert mock_orch.execute_phase.call_args[0][0] == "scene_assembling"
        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "subtitle_generating"
        assert {a.kind for a in saved.artifacts} == {"tts_audio", "scene_segment"}

    def test_parallel_primary_failure_keeps_parallel_success_artifacts(self) -> None:
        """并行主 phase 失败时，同 tick 成功的 tts_audio 指针不得被丢弃。"""
        record = make_record(phase="scene_assembling", mode="import")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "scene_assembling"
        assert saved.execution.status == "retrying"
        assert [a.kind for a in saved.artifacts] == ["tts_audio"]

    def test_parallel_tts_failure_is_attributed_to_tts_phase(self) -> None:
        """并行 TTS 失败不得"成功"推进，失败须归因到 tts_generating。"""
        record = make_record(phase="scene_assembling", mode="import")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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


# ---------------------------------------------------------------------------
# 13. TTS failure semantics (#253)
# ---------------------------------------------------------------------------


class TestTTSFailureSemantics:
    """TTS synthesis failures keep job at tts_generating, never advance to tts_review."""

    def test_tts_retryable_failure_stays_in_phase(self) -> None:
        """retryable TTS failure → phase stays tts_generating, status retrying."""
        record = make_record(phase="tts_generating", mode="generate")
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionFailure(
            error=ExecutionFailure(
                code="TTS_SYNTHESIS_FAILED",
                message="TTS synthesis failed: network error",
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
        assert saved.phase == "tts_generating"
        assert saved.execution.status == "retrying"
        assert saved.execution.current_attempt == 1
        assert saved.execution.error is not None
        assert saved.execution.error.code == "TTS_SYNTHESIS_FAILED"
        assert saved.execution.error.retryable is True
        # Must not advance to tts_review
        assert saved.phase != "tts_review"

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

    @pytest.mark.parametrize(
        ("attempt", "expected_phase", "expected_status"),
        [
            (0, "tts_generating", "retrying"),
            (1, "tts_generating", "retrying"),
            (2, "failed", "failed"),
        ],
    )
    def test_tts_retryable_failure_exhausts_after_three(
        self, attempt: int, expected_phase: str, expected_status: str
    ) -> None:
        """3 retryable TTS failures → terminal failed."""
        record = make_record(phase="tts_generating", mode="generate")
        if attempt:
            record.execution = record.execution.model_copy(
                update={"status": "retrying", "current_attempt": attempt}
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
        assert saved.phase == expected_phase
        assert saved.execution.status == expected_status
        assert saved.execution.current_attempt == attempt + 1
        if expected_status == "failed":
            assert saved.failed_phase == "tts_generating"

    def test_tts_failure_preserves_upstream_script_artifact(self) -> None:
        """TTS failure preserves script artifact — only tts_audio is absent."""
        script_artifact = ArtifactPointer(kind="script", relative_path="script.txt")
        record = make_record(phase="tts_generating", mode="generate")
        record.artifacts = [script_artifact]
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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

        saved = mock_repo.save_job.call_args[0][1]
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
        """Non-retryable montage failure → terminal failed, phase=montage_assembling."""
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
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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
        """Retryable montage failure → stays in phase, upstream artifacts preserved."""
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
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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

        saved = mock_repo.save_job.call_args[0][1]
        # Phase stays at montage_assembling (retrying).
        assert saved.phase == "montage_assembling"
        assert saved.failed_phase is None
        assert saved.execution.status == "retrying"
        assert saved.execution.current_attempt == 1
        assert saved.execution.error is not None
        assert saved.execution.error.retryable is True
        # Upstream artifacts are preserved.
        artifact_kinds = {a.kind for a in saved.artifacts}
        assert "tts_audio" in artifact_kinds
        assert "selected_clips" in artifact_kinds

    def test_retryable_failure_exhausts_after_max_attempts(self) -> None:
        """When max_attempts are exhausted, montage_assembling failure is terminal."""
        record = make_record(
            phase="montage_assembling",
            mode="generate",
            execution=PhaseExecutionState(
                status="retrying",
                current_attempt=2,
                max_attempts=3,
            ),
            artifacts=[
                ArtifactPointer(
                    kind="tts_audio", relative_path="audio.mp3", size_bytes=100
                ),
            ],
        )
        mock_repo = Mock(spec=FileStoreRepository)
        mock_repo.load_job.return_value = record
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

        saved = mock_repo.save_job.call_args[0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "montage_assembling"
        assert saved.execution.status == "failed"
        # Upstream artifacts are preserved even on terminal failure.
        artifact_kinds = {a.kind for a in saved.artifacts}
        assert "tts_audio" in artifact_kinds
