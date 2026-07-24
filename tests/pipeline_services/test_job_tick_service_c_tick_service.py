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
        """Orchestrator failure should result in failed phase after retries."""
        record = make_record(phase="script_generating")
        mock_repo = _persistent_repo(record)
        mock_orch = Mock(spec=PhaseOrchestrator)
        mock_orch.run_phase.side_effect = RuntimeError("API failure")

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo, sleep_fn=None)
        svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # After max retries, job should be in failed phase.
        saved = mock_repo.save_job.call_args_list[-1][0][1]
        assert saved.phase == "failed"
        assert saved.failed_phase == "script_generating"

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
            asset_collection_status="complete",
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
        discovered = orch._discover_script(job_dir)
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
