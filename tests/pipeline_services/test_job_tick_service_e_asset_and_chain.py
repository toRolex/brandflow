"""Tests for _compute_transition pure state machine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

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
        record = record.model_copy(update={"asset_collection_status": "complete"})

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
        record = record.model_copy(update={"asset_collection_status": "complete"})

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
        record = record.model_copy(update={"asset_collection_status": "complete"})

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
# 14. Auto-approve asset_review with collection status gating (#326)
# ---------------------------------------------------------------------------


class TestAutoApproveCollectionStatus:
    """The auto-approve integrity check must respect asset_collection_status."""

    def test_blocked_when_collection_not_started(self, tmp_path: Path) -> None:
        """asset_collection_status='not_started' → blocked, stays in asset_review."""

        job_id = "test-cs-not-started"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # No selected_clips.json written — simulates "not started"
        record = make_record(
            phase="asset_review",
            auto_approve=True,
            review_status="none",
        )
        record.job_id = job_id
        # Explicitly set to not_started (same as default, but explicit for clarity)
        record = record.model_copy(update={"asset_collection_status": "not_started"})

        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        saved = repo.load_job("proj-001", job_id)
        assert saved.phase == "asset_review", (
            f"Expected asset_review (blocked), got {saved.phase}"
        )
        assert saved.review_status == "pending", (
            f"Expected pending review, got {saved.review_status}"
        )

    def test_blocked_when_collection_collecting(self, tmp_path: Path) -> None:
        """asset_collection_status='collecting' → blocked, handler still running."""
        job_id = "test-cs-collecting"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # No selected_clips.json — handler hasn't finished yet
        record = make_record(
            phase="asset_review",
            auto_approve=True,
            review_status="none",
        )
        record.job_id = job_id
        record = record.model_copy(update={"asset_collection_status": "collecting"})

        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        saved = repo.load_job("proj-001", job_id)
        assert saved.phase == "asset_review", (
            f"Expected asset_review (blocked), got {saved.phase}"
        )
        assert saved.review_status == "pending", (
            f"Expected pending review, got {saved.review_status}"
        )

    def test_blocked_when_collection_empty(self, tmp_path: Path) -> None:
        """asset_collection_status='complete_empty' → blocked, requires human."""

        job_id = "test-cs-empty"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Write empty selected_clips.json
        (job_dir / "selected_clips.json").write_text("[]", encoding="utf-8")

        record = make_record(
            phase="asset_review",
            auto_approve=True,
            review_status="none",
        )
        record.job_id = job_id
        record = record.model_copy(update={"asset_collection_status": "complete_empty"})

        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        saved = repo.load_job("proj-001", job_id)
        assert saved.phase == "asset_review", (
            f"Expected asset_review (blocked), got {saved.phase}"
        )
        assert saved.review_status == "pending", (
            f"Expected pending review, got {saved.review_status}"
        )

    def test_proceeds_when_collection_complete(self, tmp_path: Path) -> None:
        """asset_collection_status='complete' → proceeds normally, writes snapshot."""
        import json as _json

        job_id = "test-cs-complete"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        clips = [
            {
                "sentence": "测试句。",
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
            phase="asset_review",
            auto_approve=True,
            review_status="none",
        )
        record.job_id = job_id
        record = record.model_copy(update={"asset_collection_status": "complete"})

        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        saved = repo.load_job("proj-001", job_id)
        assert saved.phase != "asset_review", (
            f"Expected advance past asset_review, got {saved.phase}"
        )
        assert saved.review_status == "approved"
        snapshot_path = job_dir / "reviewed_assets.json"
        assert snapshot_path.exists(), "reviewed_assets.json should be written"

    def test_proceeds_when_missing_file_but_status_complete(
        self, tmp_path: Path
    ) -> None:
        """Status='complete' trusts the handler: proceeds even if file is missing
        (supports mock tests and async-worker scenarios)."""
        job_id = "test-cs-missing-file"
        root_dir = tmp_path
        project_dir = root_dir / "workspace" / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # Intentionally do NOT write selected_clips.json
        record = make_record(
            phase="asset_review",
            auto_approve=True,
            review_status="none",
        )
        record.job_id = job_id
        record = record.model_copy(update={"asset_collection_status": "complete"})

        from packages.file_store.repository import FileStoreRepository

        repo = FileStoreRepository(root_dir)
        repo.save_job("proj-001", record)

        mock_orch = Mock(spec=PhaseOrchestrator)
        svc = JobTickService(mock_orch, repo)

        svc.tick(
            "proj-001", job_id, "product", root_dir=root_dir, project_dir=project_dir
        )

        saved = repo.load_job("proj-001", job_id)
        assert saved.phase != "asset_review", (
            f"Expected advance past asset_review, got {saved.phase}"
        )
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
        record = make_record(
            phase="queued",
            mode="generate",
            auto_approve=True,
            asset_collection_status="complete",
        )
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
        # Three calls: (1) tick entry, (2) lifecycle check inside _tick_step,
        # (3) loop reload between chain steps.
        repo.load_job.side_effect = [record_queued, record_queued, record_cancelled]
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
