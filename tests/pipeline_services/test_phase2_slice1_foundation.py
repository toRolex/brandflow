"""Tests for Phase 2 Slice 1 — dual-mode infrastructure foundation.

Covers:
- ProductionMode type and JobRecord.mode field
- New phases in Phase / PHASE_ORDER
- Import mode transition routing in _compute_transition
- Generate mode preserves existing flow
- Import mode skips script_review/tts_review defensively
- run_phases_parallel dispatch
- Skeleton handlers for scene_assembling / montage_assembling
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, MagicMock

import pytest

from packages.domain_core.models import (
    JobRecord,
    Phase,
    ProductionMode,
)
from packages.domain_core.state import PHASE_ORDER, next_phase
from packages.pipeline_services.job_tick_service import (
    HANDLED_PHASES,
    REVIEW_PHASES,
    JobTickService,
    TickAction,
    _compute_transition,
    _safe_next,
)
from packages.pipeline_services.phase_orchestrator import (
    ArtifactPointer,
    PhaseContext,
    PhaseOrchestrator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_record(
    phase: str = "queued",
    mode: ProductionMode = "generate",
    review_status: str = "none",
    auto_approve: bool = False,
    **kwargs,
) -> JobRecord:
    """Factory for concise test construction."""
    return JobRecord(
        job_id="test-job",
        project_id="proj-001",
        product="羊肚菌",
        phase=phase,  # type: ignore[arg-type]
        mode=mode,
        review_status=review_status,  # type: ignore[arg-type]
        auto_approve=auto_approve,
        **kwargs,
    )


def _next(phase: str) -> str:
    """Return the expected next phase (matching domain_core.state.next_phase)."""
    idx = PHASE_ORDER.index(phase)
    if idx >= len(PHASE_ORDER) - 1:
        return "completed"
    return PHASE_ORDER[idx + 1]


# ---------------------------------------------------------------------------
# 1. ProductionMode type and JobRecord.mode field
# ---------------------------------------------------------------------------


class TestProductionMode:
    def test_mode_defaults_to_generate(self) -> None:
        """JobRecord.mode defaults to 'generate' for backward compatibility."""
        record = make_record()
        assert record.mode == "generate"

    def test_mode_import(self) -> None:
        """Import mode can be set explicitly."""
        record = make_record(mode="import")
        assert record.mode == "import"

    def test_mode_generate(self) -> None:
        """Generate mode can be set explicitly."""
        record = make_record(mode="generate")
        assert record.mode == "generate"


# ---------------------------------------------------------------------------
# 2. New phases in type system and PHASE_ORDER
# ---------------------------------------------------------------------------


class TestNewPhases:
    def test_scene_assembling_in_phase_literal(self) -> None:
        """scene_assembling is a valid Phase value."""
        # This is a compile-time type check via the factory
        record = make_record(phase="scene_assembling")
        assert record.phase == "scene_assembling"

    def test_montage_assembling_in_phase_literal(self) -> None:
        """montage_assembling is a valid Phase value."""
        record = make_record(phase="montage_assembling")
        assert record.phase == "montage_assembling"

    def test_phases_in_phase_order(self) -> None:
        """Both new phases appear in PHASE_ORDER."""
        assert "scene_assembling" in PHASE_ORDER
        assert "montage_assembling" in PHASE_ORDER

    def test_phases_after_completed(self) -> None:
        """New phases are placed after 'completed' so GENERATE flow is unaffected."""
        completed_idx = PHASE_ORDER.index("completed")
        scene_idx = PHASE_ORDER.index("scene_assembling")
        montage_idx = PHASE_ORDER.index("montage_assembling")
        assert scene_idx > completed_idx
        assert montage_idx > completed_idx

    def test_safe_next_stops_at_completed(self) -> None:
        """_safe_next('completed') returns 'completed' (not scene_assembling)."""
        assert _safe_next("completed") == "completed"

    def test_phase_order_preserves_generate_flow_order(self) -> None:
        """GENERATE flow phases remain in correct relative order."""
        for a, b in [
            ("queued", "script_generating"),
            ("script_generating", "script_review"),
            ("script_review", "tts_generating"),
            ("tts_generating", "tts_review"),
            ("tts_review", "subtitle_generating"),
            ("subtitle_generating", "asset_retrieving"),
            ("asset_retrieving", "asset_review"),
            ("asset_review", "video_rendering"),
            ("video_rendering", "final_rendering"),
            ("final_rendering", "final_review"),
            ("final_review", "completed"),
        ]:
            assert _safe_next(a) == b, f"{a} → {b}"


# ---------------------------------------------------------------------------
# 3. Import mode transition routing in _compute_transition
# ---------------------------------------------------------------------------


class TestImportModeQueued:
    def test_queued_import_advances_to_scene_assembling(self) -> None:
        """queued + import → advance to scene_assembling (no handler)."""
        action = _compute_transition(make_record(phase="queued", mode="import"), ())
        assert action.run_handler is False
        assert action.new_phase == "scene_assembling"
        assert action.message == "queued → scene_assembling (import mode, no handler yet)"

    def test_queued_import_does_not_run_script_handler(self) -> None:
        """Import mode should NOT route to script_generating."""
        action = _compute_transition(make_record(phase="queued", mode="import"), ())
        assert action.handler_phase is None or action.handler_phase != "script_generating"


class TestImportModeSceneAssembling:
    def test_scene_assembling_parallel_dispatch(self) -> None:
        """scene_assembling + import → parallel dispatch with tts_generating."""
        action = _compute_transition(make_record(phase="scene_assembling", mode="import"), ())
        assert action.run_handler is True
        assert action.handler_phase == "scene_assembling"
        assert action.parallel_phases == ["tts_generating"]
        assert action.new_phase == "montage_assembling"

    def test_scene_assembling_generate_mode(self) -> None:
        """scene_assembling + generate mode is handled normally."""
        action = _compute_transition(make_record(phase="scene_assembling", mode="generate"), ())
        # With generate mode, scene_assembling should also work (defensive)
        assert action.run_handler is True
        assert action.handler_phase == "scene_assembling"


class TestImportModeMontageAssembling:
    def test_montage_assembling_advances_to_asset_retrieving(self) -> None:
        """montage_assembling → advance to asset_retrieving."""
        action = _compute_transition(
            make_record(phase="montage_assembling", mode="import"), ()
        )
        assert action.new_phase == "asset_retrieving"
        assert action.run_handler is False

    def test_montage_assembling_generate_mode(self) -> None:
        """montage_assembling + generate mode routes to asset_retrieving."""
        action = _compute_transition(
            make_record(phase="montage_assembling", mode="generate"), ()
        )
        assert action.new_phase == "asset_retrieving"


# ---------------------------------------------------------------------------
# 4. Generate mode preserves existing flow
# ---------------------------------------------------------------------------


class TestGenerateModeQueued:
    def test_queued_generate_routes_to_script_generating(self) -> None:
        """queued + generate → routes to script_generating handler."""
        action = _compute_transition(make_record(phase="queued", mode="generate"), ())
        assert action.run_handler is True
        assert action.handler_phase == "script_generating"
        assert action.new_phase is None
        assert action.new_review_status is None

    def test_queued_default_mode_is_generate(self) -> None:
        """Default (no explicit mode) → generate behavior."""
        action = _compute_transition(make_record(phase="queued"), ())
        assert action.handler_phase == "script_generating"


# ---------------------------------------------------------------------------
# 5. Import mode skips script_review/tts_review defensively
# ---------------------------------------------------------------------------


class TestImportModeSkipReviews:
    @pytest.mark.parametrize("phase", ["script_review", "tts_review"])
    def test_import_mode_skips_review_phase(self, phase: str) -> None:
        """Import mode at script_review or tts_review → auto-advance."""
        action = _compute_transition(
            make_record(phase=phase, mode="import"), ()
        )
        assert action.run_handler is False
        assert action.new_phase is not None
        assert f"skip {phase}" in action.message

    @pytest.mark.parametrize("phase", ["script_review", "tts_review"])
    def test_generate_mode_does_not_skip(self, phase: str) -> None:
        """Generate mode should handle script_review/tts_review normally."""
        action = _compute_transition(
            make_record(phase=phase, mode="generate", auto_approve=True), ()
        )
        # With auto_approve, should advance with approved status
        assert action.new_phase is not None
        assert action.new_review_status == "approved"

    @pytest.mark.parametrize("phase", ["asset_review", "final_review"])
    def test_import_mode_preserves_asset_final_review(self, phase: str) -> None:
        """Import mode should NOT skip asset_review or final_review."""
        action = _compute_transition(
            make_record(phase=phase, mode="import", review_status="pending"), ()
        )
        # Should wait for human review (empty action)
        assert action.run_handler is False
        assert action.new_phase is None


# ---------------------------------------------------------------------------
# 6. run_phases_parallel dispatch
# ---------------------------------------------------------------------------


class TestRunPhasesParallel:
    def test_executes_all_phases(self) -> None:
        """run_phases_parallel executes every phase in the list."""
        orch = PhaseOrchestrator(*[MagicMock()] * 4)
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=Path("/tmp/proj"),
            root_dir=Path("/tmp"),
            product="test",
        )
        results = orch.run_phases_parallel(
            ["scene_assembling", "tts_generating"], ctx
        )
        assert "scene_assembling" in results
        assert "tts_generating" in results

    def test_returns_dict_of_lists(self) -> None:
        """Returns dict[str, list[ArtifactPointer]]."""
        orch = PhaseOrchestrator(*[MagicMock()] * 4)
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=Path("/tmp/proj"),
            root_dir=Path("/tmp"),
            product="test",
        )
        results = orch.run_phases_parallel(["scene_assembling"], ctx)
        assert isinstance(results, dict)
        assert isinstance(results["scene_assembling"], list)

    def test_no_one_phase_crash_kills_all(self) -> None:
        """One failing phase should not prevent other phases from completing."""
        orch = PhaseOrchestrator(*[MagicMock()] * 4)
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=Path("/tmp/proj"),
            root_dir=Path("/tmp"),
            product="test",
        )
        # Inject a failing handler
        def _failing(_ctx):
            raise RuntimeError("oh no")

        orch._handlers["scene_assembling"] = _failing
        results = orch.run_phases_parallel(
            ["scene_assembling", "montage_assembling"], ctx
        )
        assert "scene_assembling" in results
        assert "montage_assembling" in results
        assert results["scene_assembling"] == []
        assert results["montage_assembling"] == []

    def test_merges_all_results_in_job_tick_service(self) -> None:
        """JobTickService.tick with parallel_phases merges all artifacts."""
        record = make_record(phase="scene_assembling", mode="import")
        mock_repo = MagicMock()
        mock_repo.load_job.return_value = record
        mock_orch = MagicMock(spec=PhaseOrchestrator)
        mock_orch.run_phases_parallel.return_value = {
            "scene_assembling": [],
            "tts_generating": [],
        }

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "羊肚菌",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )
        mock_orch.run_phases_parallel.assert_called_once_with(
            ["scene_assembling", "tts_generating"], ANY
        )
        assert summary.action in ("advanced", "skipped")


# ---------------------------------------------------------------------------
# 7. Skeleton handlers
# ---------------------------------------------------------------------------


class TestSkeletonHandlers:
    def test_scene_assembly_returns_empty_list(self) -> None:
        """scene_assembling skeleton returns []."""
        orch = PhaseOrchestrator(*[MagicMock()] * 4)
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=Path("/tmp/proj"),
            root_dir=Path("/tmp"),
            product="test",
        )
        result = orch.run_phase("scene_assembling", ctx)
        assert result == []

    def test_montage_assembly_returns_empty_list(self) -> None:
        """montage_assembling skeleton returns []."""
        orch = PhaseOrchestrator(*[MagicMock()] * 4)
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=Path("/tmp/proj"),
            root_dir=Path("/tmp"),
            product="test",
        )
        result = orch.run_phase("montage_assembling", ctx)
        assert result == []

    def test_handlers_are_registered_in_map(self) -> None:
        """Both new handlers are registered in the handler map."""
        orch = PhaseOrchestrator(*[MagicMock()] * 4)
        assert "scene_assembling" in orch._handlers
        assert "montage_assembling" in orch._handlers


# ---------------------------------------------------------------------------
# 8. Import mode full flow integration
# ---------------------------------------------------------------------------


class TestImportModeFullFlow:
    """End-to-end transition sequence for import mode."""

    def test_queued_to_completed_sequence(self) -> None:
        """Verify the expected import mode phase sequence."""
        # Build sequence of transitions in import mode
        sequence = [
            ("queued", "scene_assembling"),  # first transition
            ("scene_assembling", "montage_assembling"),  # after parallel dispatch
            ("montage_assembling", "asset_retrieving"),  # explicit route
            ("asset_retrieving", "asset_review"),  # standard flow resumes
            ("asset_review", "video_rendering"),
            ("video_rendering", "final_rendering"),
            ("final_rendering", "final_review"),
            ("final_review", "completed"),
        ]
        for from_phase, to_phase in sequence:
            action = _compute_transition(
                make_record(phase=from_phase, mode="import", auto_approve=False), ()
            )
            if from_phase == "queued":
                assert action.new_phase == to_phase, f"{from_phase} → {to_phase}"
            elif from_phase == "scene_assembling":
                assert action.run_handler is True
                assert action.new_phase == "montage_assembling"
            elif from_phase == "montage_assembling":
                assert action.new_phase == to_phase, f"{from_phase} → {to_phase}"
            elif from_phase == "asset_retrieving":
                # At asset_retrieving, empty artifacts → auto-advance
                pass  # handled by _transition_after_artifacts
            elif from_phase == "asset_review":
                # No artifacts and pending review → wait
                assert action.new_phase is None
            elif from_phase == "final_review":
                # No artifacts and pending review → wait
                assert action.new_phase is None
            elif from_phase == "video_rendering":
                # No artifacts → retry logic
                assert action.run_handler is True

    def test_import_mode_with_auto_approve_advances_through_gates(self) -> None:
        """Import mode with auto_approve=True advances through review gates."""
        for phase in ["asset_review", "final_review"]:
            action = _compute_transition(
                make_record(phase=phase, mode="import", auto_approve=True), ()
            )
            assert action.new_phase is not None, f"{phase} should auto-advance with auto_approve"
            assert action.new_review_status == "approved"
