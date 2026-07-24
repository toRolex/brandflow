"""Tests for _compute_transition pure state machine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock


from packages.domain_core.models import (
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
    JobTickService,
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


class TestImportSceneInput:
    """Import jobs require valid scene folders and fail non-retryably."""

    def test_import_job_with_empty_scene_folder_ids_skips_scene_assembling(
        self,
    ) -> None:
        """An import job queued without selected scene folders skips scene_assembling
        and goes directly to tts_generating handler with target subtitle_generating."""
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = []
        action = _compute_transition(record, ())
        assert action.run_handler is True
        assert action.handler_phase == "tts_generating"
        assert action.new_phase == "subtitle_generating"

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

    def test_queued_generate_job_does_not_require_scene_folders(self) -> None:
        record = make_record(phase="queued", mode="generate")
        record.scene_folder_ids = []
        action = _compute_transition(record, ())
        assert action.new_phase is None
        assert action.handler_phase == "script_generating"


class TestImportSceneFolderFallback:
    """#275: tick() fallback scene_folder_ids from scene config for import mode."""

    def test_tick_import_empty_folders_with_scene_config_skips_scene_assembling(
        self,
    ) -> None:
        """import + empty scene_folder_ids + product scene config → skips scene_assembling,
        goes to tts_generating handler with target subtitle_generating."""
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = []
        mock_repo = _persistent_repo(record)
        mock_orch = Mock()
        mock_orch.execute_phase.side_effect = lambda phase, ctx: PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")]
        )
        mock_orch.run_phase.return_value = []
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

        # Job advances past queued; must NOT go to migration_required or scene_assembling.
        assert summary.action == "advanced"
        assert summary.to_phase not in (
            "migration_required",
            "scene_assembling",
            "queued",
        )

    def test_tick_import_empty_folders_no_scene_config_skips_scene_assembling(
        self,
    ) -> None:
        """import + empty scene_folder_ids + no product scene config → skips scene_assembling,
        goes to tts_generating handler with target subtitle_generating."""
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = []
        mock_repo = _persistent_repo(record)
        mock_orch = Mock()
        mock_orch.execute_phase.side_effect = lambda phase, ctx: PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")]
        )
        mock_orch.run_phase.return_value = []
        mock_config = Mock()
        mock_config.get_scene_config.return_value = {"folders": []}

        svc = JobTickService(
            orchestrator=mock_orch,
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

        # Job advances past queued; must NOT go to migration_required or scene_assembling.
        assert summary.action == "advanced"
        assert summary.to_phase not in (
            "migration_required",
            "scene_assembling",
            "queued",
        )

    def test_tick_import_with_existing_folders_unaffected(self) -> None:
        """import + existing scene_folder_ids → behavior unchanged, no config fallback."""
        record = make_record(phase="queued", mode="import")
        record.scene_folder_ids = ["scenes/existing"]
        mock_repo = _persistent_repo(record)
        mock_orch = Mock()
        mock_orch.execute_phases_parallel.return_value = {
            "scene_assembling": PhaseExecutionSuccess(
                artifacts=[
                    ArtifactPointer(kind="scene_segment", relative_path="scene.mp4")
                ]
            ),
            "tts_generating": PhaseExecutionSuccess(artifacts=[]),
        }
        mock_orch.execute_phase.side_effect = lambda phase, ctx: PhaseExecutionSuccess(
            artifacts=[ArtifactPointer(kind="tts_audio", relative_path="audio.mp3")]
        )
        mock_orch.run_phase.return_value = []
        mock_config = Mock()
        mock_config.get_scene_config.return_value = {
            "folders": [],
            "transition_duration_ms": 500,
        }

        svc = JobTickService(
            orchestrator=mock_orch,
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
        # get_scene_config is called by _build_phase_context for import jobs
        # (transition_duration_ms + fallback folder list), but the existing
        # scene_folder_ids on the record take precedence.
        # _build_phase_context rebuilds ctx for each handler attempt (once per
        # phase step in the chain — scene_assembling, subtitle_generating, …).
        assert mock_config.get_scene_config.call_count == 3

    def test_tick_generate_job_unaffected_by_scene_config(self) -> None:
        """generate mode → unaffected by scene config fallback."""
        record = make_record(phase="queued", mode="generate")
        mock_repo = _persistent_repo(record)
        mock_orch = Mock()
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
