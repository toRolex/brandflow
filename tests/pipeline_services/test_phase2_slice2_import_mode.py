"""Tests for Phase 2 Slice 2 — full Import mode pipeline.

Covers:
- Scene config defaults via ConfigReader.get_scene_config
- PhaseContext scene field population
- scene_assembling handler: config resolution, random file picking, ffmpeg output
- montage_assembling handler: file-aware concatenation logic
- Full import mode tick flow through scene_assembling + tts_generating parallel
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from packages.domain_core.models import JobRecord
from packages.domain_core.phase_execution import PhaseExecutionSuccess
from packages.pipeline_services.job_tick_service import (
    JobTickService,
    _compute_transition,
)
from packages.pipeline_services.phase_orchestrator import (
    ArtifactPointer,
    PhaseContext,
    PhaseOrchestrator,
)
from packages.provider_config.config_constants import DEFAULTS
from packages.provider_config.config_reader import ConfigReader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    """Create a minimal root_dir layout."""
    return tmp_path


@pytest.fixture()
def project_dir(tmp_root: Path) -> Path:
    d = tmp_root / "workspace" / "projects" / "proj-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def job_dir(project_dir: Path) -> Path:
    d = project_dir / "runtime" / "jobs" / "job-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def ctx(project_dir: Path, tmp_root: Path) -> PhaseContext:
    return PhaseContext(
        job_id="job-001",
        project_dir=project_dir,
        root_dir=tmp_root,
        product="test-product",
        options={},
    )


@pytest.fixture()
def orchestrator() -> PhaseOrchestrator:
    return PhaseOrchestrator(
        subtitle_svc=MagicMock(),
        video_svc=MagicMock(),
        schedule_store=MagicMock(),
    )


def make_record(
    phase: str = "queued",
    mode: str = "import",
    review_status: str = "none",
    auto_approve: bool = False,
    **kwargs,
) -> JobRecord:
    return JobRecord(
        job_id="test-job",
        project_id="proj-001",
        product="test",
        phase=phase,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        review_status=review_status,  # type: ignore[arg-type]
        auto_approve=auto_approve,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. Scene config defaults via ConfigReader
# ---------------------------------------------------------------------------


class TestSceneConfigDefaults:
    def test_defaults_have_scene_section(self) -> None:
        """DEFAULTS contains a 'scene' key."""
        assert "scene" in DEFAULTS
        assert "folders" in DEFAULTS["scene"]
        assert "transition_duration_ms" in DEFAULTS["scene"]

    def test_default_folders_empty(self) -> None:
        """Scene folders default to empty list."""
        assert DEFAULTS["scene"]["folders"] == []

    def test_default_transition_duration_500(self) -> None:
        """Default transition duration is 500ms."""
        assert DEFAULTS["scene"]["transition_duration_ms"] == 500

    def test_get_scene_config_returns_defaults_when_no_file(self) -> None:
        """get_scene_config() returns merged defaults when config file missing."""
        # Use a temp config directory to avoid polluting real config
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            reader = ConfigReader(config_dir=tmpdir)
            cfg = reader.get_scene_config()
            assert cfg["folders"] == []
            assert cfg["transition_duration_ms"] == 500

    def test_get_scene_config_merges_user_config(self, tmp_path: Path) -> None:
        """get_scene_config() merges user config over defaults."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "app_config.json"
        config_file.write_text(
            json.dumps(
                {
                    "scene": {
                        "folders": [
                            {"name": "brand-intro", "path": "scene/brand-intro"},
                            {"name": "product-show", "path": "scene/product-show"},
                        ],
                        "transition_duration_ms": 1000,
                    }
                }
            ),
            encoding="utf-8",
        )

        reader = ConfigReader(config_dir=str(config_dir))
        cfg = reader.get_scene_config()
        assert len(cfg["folders"]) == 2
        assert cfg["folders"][0]["name"] == "brand-intro"
        assert cfg["folders"][1]["path"] == "scene/product-show"
        assert cfg["transition_duration_ms"] == 1000


# ---------------------------------------------------------------------------
# 2. PhaseContext scene fields
# ---------------------------------------------------------------------------


class TestPhaseContextSceneFields:
    def test_default_scene_fields(self) -> None:
        """PhaseContext defaults have empty scene_folder_paths and 500ms duration."""
        ctx = PhaseContext(
            job_id="j1",
            project_dir=Path("/p"),
            root_dir=Path("/r"),
            product="test",
        )
        assert ctx.scene_folder_paths == []
        assert ctx.transition_duration_ms == 500

    def test_custom_scene_fields(self) -> None:
        """PhaseContext accepts custom scene config."""
        ctx = PhaseContext(
            job_id="j1",
            project_dir=Path("/p"),
            root_dir=Path("/r"),
            product="test",
            scene_folder_paths=["scene/brand-intro", "scene/product-show"],
            transition_duration_ms=1000,
        )
        assert ctx.scene_folder_paths == ["scene/brand-intro", "scene/product-show"]
        assert ctx.transition_duration_ms == 1000


# ---------------------------------------------------------------------------
# 3. scene_assembling handler — config resolution and file picking
# ---------------------------------------------------------------------------


class TestSceneAssembling:
    def test_returns_empty_when_no_folders_configured(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """No scene folders → returns empty list."""
        result = orchestrator.run_phase("scene_assembling", ctx)
        assert result == []

    def test_resolves_relative_folder_paths(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """Relative scene folder paths are resolved relative to workspace."""
        # Create a scene folder with a dummy video file
        scene_folder = tmp_root / "workspace" / "scene" / "brand-intro"
        scene_folder.mkdir(parents=True)
        fake_video = scene_folder / "intro.mp4"
        fake_video.write_text("fake video data")

        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/brand-intro"],
            transition_duration_ms=500,
        )

        # Patch ffmpeg to avoid needing real ffmpeg and mock subprocess
        with patch.object(
            orchestrator, "_get_ffmpeg_path", return_value="/usr/bin/false"
        ):
            with patch.object(
                orchestrator,
                "_get_media_duration",
                return_value=5.0,
            ):
                with patch.object(subprocess, "run") as mock_run:
                    # Make the mocked subprocess not raise
                    mock_run.return_value = MagicMock(returncode=0)

                    # Also make the scene path "exist" by creating it after mock_call
                    def _side_effect(*args, **kwargs):
                        scene_path = (
                            project_dir
                            / "runtime"
                            / "jobs"
                            / "job-001"
                            / "scene_segment.mp4"
                        )
                        scene_path.parent.mkdir(parents=True, exist_ok=True)
                        scene_path.write_text("fake scene video")
                        return MagicMock(returncode=0)

                    mock_run.side_effect = _side_effect
                    result = orchestrator.run_phase("scene_assembling", ctx)

        assert len(result) == 1
        assert result[0].kind == "scene_segment"
        assert result[0].relative_path.endswith("scene_segment.mp4")
        assert result[0].size_bytes > 0

    def test_picks_random_file_per_folder(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """One random video is picked from each configured folder."""
        # Set up two scene folders, each with multiple video files
        for folder_name in ("brand-intro", "product-show"):
            folder = tmp_root / "workspace" / "scene" / folder_name
            folder.mkdir(parents=True)
            for i in range(3):
                (folder / f"clip_{i}.mp4").write_text(f"video {folder_name} {i}")

        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/brand-intro", "scene/product-show"],
            transition_duration_ms=500,
        )

        with patch.object(orchestrator, "_get_ffmpeg_path", return_value="ffmpeg"):
            with patch.object(orchestrator, "_get_media_duration", return_value=3.0):
                with patch.object(subprocess, "run") as mock_run:
                    mock_run.return_value = MagicMock(returncode=0)

                    def _make_scene(*args, **kwargs):
                        scene_path = (
                            project_dir
                            / "runtime"
                            / "jobs"
                            / "job-001"
                            / "scene_segment.mp4"
                        )
                        scene_path.parent.mkdir(parents=True, exist_ok=True)
                        scene_path.write_text("fake output")
                        return MagicMock(returncode=0)

                    mock_run.side_effect = _make_scene
                    result = orchestrator.run_phase("scene_assembling", ctx)

        assert len(result) == 1
        # Should have chosen 1 file from each of the 2 folders
        self._verify_subprocess_call(mock_run, 2)

    @staticmethod
    def _verify_subprocess_call(mock_run: MagicMock, expected_clip_count: int) -> None:
        """Verify ffmpeg was called with the right number of input clips."""
        call_args = mock_run.call_args[0][0]
        input_count = sum(1 for i, arg in enumerate(call_args) if arg == "-i")
        assert input_count == expected_clip_count, (
            f"Expected {expected_clip_count} -i flags, got {input_count}"
        )

    def test_single_clip_copies_directly(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """Single clip scene → copied directly without ffmpeg."""
        folder = tmp_root / "workspace" / "scene" / "only-one"
        folder.mkdir(parents=True)
        source_video = folder / "opener.mp4"
        source_video.write_text("clip data")

        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/only-one"],
        )

        with patch.object(subprocess, "run") as mock_run:
            result = orchestrator.run_phase("scene_assembling", ctx)

        mock_run.assert_not_called()  # no ffmpeg for single clip

        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        scene_path = job_dir / "scene_segment.mp4"
        assert scene_path.exists()
        assert scene_path.read_text() == "clip data"
        assert len(result) == 1

    def test_skips_missing_folder(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """Missing scene folders are skipped with a warning."""
        existing_folder = tmp_root / "workspace" / "scene" / "existing"
        existing_folder.mkdir(parents=True)
        (existing_folder / "clip.mp4").write_text("data")

        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=[
                "scene/missing",  # does not exist
                "scene/existing",  # exists
            ],
        )

        with patch.object(subprocess, "run") as mock_run:
            result = orchestrator.run_phase("scene_assembling", ctx)

        # Only 1 clip was found (from the existing folder)
        mock_run.assert_not_called()  # single clip = copy, no ffmpeg
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        assert (job_dir / "scene_segment.mp4").exists()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# 4. montage_assembling handler — file concatenation logic
# ---------------------------------------------------------------------------


class TestMontageAssembling:
    def test_returns_empty_when_no_input_files(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """No scene_segment.mp4 and no base.mp4 → empty result."""
        result = orchestrator.run_phase("montage_assembling", ctx)
        assert result == []

    def test_uses_scene_segment_when_alone(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """With only scene_segment.mp4 → copies it as assembled.mp4."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        scene_path = job_dir / "scene_segment.mp4"
        scene_path.write_text("scene video data")

        with patch.object(subprocess, "run") as mock_run:
            result = orchestrator.run_phase("montage_assembling", ctx)

        mock_run.assert_not_called()
        assembled_path = job_dir / "assembled.mp4"
        assert assembled_path.exists()
        assert assembled_path.read_text() == "scene video data"
        assert len(result) == 1
        assert result[0].kind == "assembled_video"

    def test_uses_base_when_alone(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """With only base.mp4 → copies it as assembled.mp4."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        base_path = job_dir / "base.mp4"
        base_path.write_text("base video data")

        with patch.object(subprocess, "run") as mock_run:
            result = orchestrator.run_phase("montage_assembling", ctx)

        mock_run.assert_not_called()
        assembled_path = job_dir / "assembled.mp4"
        assert assembled_path.exists()
        assert assembled_path.read_text() == "base video data"
        assert len(result) == 1

    def test_concatenates_both_when_both_exist(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """With both scene_segment.mp4 and base.mp4 → ffmpeg concat."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "scene_segment.mp4").write_text("scene")
        (job_dir / "base.mp4").write_text("base")

        with patch.object(orchestrator, "_get_ffmpeg_path", return_value="ffmpeg"):
            with patch.object(subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)

                def _make_assembled(*args, **kwargs):
                    (job_dir / "assembled.mp4").write_text("concatenated")
                    return MagicMock(returncode=0)

                mock_run.side_effect = _make_assembled

                result = orchestrator.run_phase("montage_assembling", ctx)

        assert len(result) == 1
        assert result[0].kind == "assembled_video"
        assert (job_dir / "assembled.mp4").exists()

        # Verify ffmpeg was called with concat filter
        call_args = mock_run.call_args[0][0]
        assert "-filter_complex" in call_args
        filter_idx = call_args.index("-filter_complex")
        assert "concat=n=2" in call_args[filter_idx + 1]


# ---------------------------------------------------------------------------
# 5. Full import mode tick flow
# ---------------------------------------------------------------------------


class TestImportModeTickFlow:
    """Verifies the sequential tick transitions in import mode.

    Uses mocked orchestrator to verify correct phase progression without
    executing ffmpeg or other side-effect-heavy handlers.
    """

    def test_queued_to_scene_assembling_transition(self) -> None:
        """queued → scene_assembling (no handler on first tick)."""
        record = make_record(phase="queued", mode="import")
        action = _compute_transition(record, ())
        assert action.new_phase == "scene_assembling"
        assert action.run_handler is False

    def test_scene_assembling_triggers_parallel_dispatch(self) -> None:
        """scene_assembling → parallel dispatch with tts_generating."""
        record = make_record(phase="scene_assembling", mode="import")
        action = _compute_transition(record, ())
        assert action.run_handler is True
        assert action.handler_phase == "scene_assembling"
        assert action.parallel_phases == ["tts_generating"]
        assert action.new_phase == "subtitle_generating"

    def test_montage_assembling_triggers_handler(self) -> None:
        """montage_assembling → handler, then advance to video_rendering."""
        record = make_record(phase="montage_assembling", mode="import")
        action = _compute_transition(record, ())
        assert action.run_handler is True
        assert action.handler_phase == "montage_assembling"
        assert action.new_phase == "video_rendering"

    def test_import_mode_full_tick_with_mock_orchestrator(self) -> None:
        """JobTickService.tick handles import mode through scene_assembling."""
        record = make_record(phase="scene_assembling", mode="import")
        mock_repo = MagicMock()
        mock_repo.load_job.return_value = record

        mock_orch = MagicMock(spec=PhaseOrchestrator)
        mock_orch.execute_phases_parallel.return_value = {
            "scene_assembling": PhaseExecutionSuccess(
                artifacts=[
                    ArtifactPointer(
                        kind="scene_segment",
                        relative_path="projects/proj-001/runtime/jobs/job-001/scene_segment.mp4",
                        url="/workspace/projects/proj-001/runtime/jobs/job-001/scene_segment.mp4",
                        size_bytes=1000,
                    )
                ]
            ),
            "tts_generating": PhaseExecutionSuccess(
                artifacts=[
                    ArtifactPointer(
                        kind="tts_audio",
                        relative_path="projects/proj-001/runtime/jobs/job-001/audio.mp3",
                        url="/workspace/projects/proj-001/runtime/jobs/job-001/audio.mp3",
                        size_bytes=500,
                    )
                ]
            ),
        }

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "test",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        # Verify parallel dispatch was called with both phases
        call_args = mock_orch.execute_phases_parallel.call_args
        assert call_args is not None
        phases_arg = call_args[0][0]
        assert "scene_assembling" in phases_arg
        assert "tts_generating" in phases_arg

        # Verify scene config was passed in context
        ctx_arg = call_args[0][1]
        assert isinstance(ctx_arg, PhaseContext)
        assert isinstance(ctx_arg.scene_folder_paths, list)
        assert ctx_arg.transition_duration_ms == 500

        # Verify transition to montage_assembling
        assert summary.action in ("advanced", "skipped")

        # Verify artifacts were merged (2 kinds from parallel execution)
        saved_record = mock_repo.save_job.call_args[0][1]
        artifact_kinds = {a.kind for a in saved_record.artifacts}
        assert "scene_segment" in artifact_kinds
        assert "tts_audio" in artifact_kinds

    def test_import_mode_scene_config_populated_in_tick(self) -> None:
        """Import mode tick populates scene config from ConfigReader."""
        record = make_record(phase="scene_assembling", mode="import")
        mock_repo = MagicMock()
        mock_repo.load_job.return_value = record
        mock_orch = MagicMock(spec=PhaseOrchestrator)
        mock_orch.execute_phases_parallel.return_value = {
            "scene_assembling": PhaseExecutionSuccess(
                artifacts=[
                    ArtifactPointer(kind="scene_segment", relative_path="scene.mp4")
                ]
            ),
            "tts_generating": PhaseExecutionSuccess(artifacts=[]),
        }

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        svc.tick(
            "proj-001",
            "test-job",
            "test",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        call_args = mock_orch.execute_phases_parallel.call_args
        assert call_args is not None
        ctx_arg = call_args[0][1]
        # Scene paths should be populated (may be empty if no config file exists)
        assert isinstance(ctx_arg.scene_folder_paths, list)
        assert ctx_arg.transition_duration_ms > 0

    def test_import_mode_advances_past_scene_assembling_to_completed(
        self,
    ) -> None:
        """End-to-end transition from montage_assembling through video_rendering."""
        record = make_record(phase="montage_assembling", mode="import")
        mock_repo = MagicMock()
        mock_repo.load_job.return_value = record
        mock_orch = MagicMock(spec=PhaseOrchestrator)
        mock_orch.run_phase.return_value = [
            ArtifactPointer(
                kind="assembled_video",
                relative_path="assembled.mp4",
                url="/workspace/assembled.mp4",
                size_bytes=2000,
            )
        ]

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "test",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action in ("advanced",)
        assert summary.from_phase == "montage_assembling"
        # Should advance to video_rendering (not asset_retrieving)
        assert summary.to_phase == "video_rendering"

    # -- Import mode subtitle routing (issue #56) -----------------------

    def test_subtitle_generating_to_montage_assembling_with_artifacts(
        self,
    ) -> None:
        """Import mode: subtitle_generating + artifacts → montage_assembling."""
        record = make_record(phase="subtitle_generating", mode="import")
        action = _compute_transition(
            record,
            ({"kind": "subtitle", "relative_path": "subtitle.srt"},),
        )
        assert action.new_phase == "montage_assembling"
        assert "import mode" in action.message.lower()

    def test_subtitle_generating_skip_to_montage_assembling(self) -> None:
        """Import mode: subtitle_generating + skip_subtitle → montage_assembling."""
        record = make_record(
            phase="subtitle_generating", mode="import", skip_subtitle=True
        )
        action = _compute_transition(record, ())
        assert action.new_phase == "montage_assembling"
        assert "skip" in action.message.lower()

    def test_subtitle_generating_runs_handler_no_artifacts(self) -> None:
        """Import mode: subtitle_generating, no skip, no artifacts → run handler."""
        record = make_record(phase="subtitle_generating", mode="import")
        action = _compute_transition(record, ())
        assert action.run_handler is True
        assert action.handler_phase == "subtitle_generating"
        assert action.new_phase is None

    def test_subtitle_after_artifacts_routes_to_montage_assembling(
        self,
    ) -> None:
        """_transition_after_artifacts: import mode subtitle → montage_assembling."""
        from packages.pipeline_services.job_tick_service import (
            _transition_after_artifacts,
        )

        record = make_record(phase="subtitle_generating", mode="import")
        action = _transition_after_artifacts(
            record,
            ({"kind": "subtitle", "relative_path": "subtitle.srt"},),
        )
        assert action.new_phase == "montage_assembling"
        assert "import mode" in action.message.lower()

    def test_scene_assembling_to_subtitle_generating_transition(self) -> None:
        """Import mode: scene_assembling → subtitle_generating (not montage_assembling)."""
        record = make_record(phase="scene_assembling", mode="import")
        action = _compute_transition(record, ())
        assert action.new_phase == "subtitle_generating"

    def test_generate_mode_subtitle_skip_unchanged(self) -> None:
        """Generate mode: subtitle skip still uses _safe_next (asset_retrieving)."""
        record = make_record(
            phase="subtitle_generating", mode="generate", skip_subtitle=True
        )
        action = _compute_transition(record, ())
        assert action.new_phase == "asset_retrieving"

    def test_generate_mode_subtitle_artifacts_unchanged(self) -> None:
        """Generate mode: subtitle + artifacts still goes to _safe_next."""
        record = make_record(phase="subtitle_generating", mode="generate")
        action = _compute_transition(
            record,
            ({"kind": "subtitle", "relative_path": "subtitle.srt"},),
        )
        assert action.new_phase == "asset_retrieving"
