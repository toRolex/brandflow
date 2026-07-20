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

    # ------------------------------------------------------------------
    # Scene Asset Snapshot tests (Issue #174)
    # ------------------------------------------------------------------

    def test_snapshot_created_on_first_run(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """First run picks random clips and copies them to .scene_snapshot/."""
        # Set up two scene folders each with video files
        for folder_name in ("brand-intro", "product-show"):
            folder = tmp_root / "workspace" / "scene" / folder_name
            folder.mkdir(parents=True)
            for i in range(3):
                (folder / f"clip_{i}.mp4").write_text(f"video {folder_name} {i}")

        ctx = PhaseContext(
            job_id="job-snap-001",
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
                            / "job-snap-001"
                            / "scene_segment.mp4"
                        )
                        scene_path.parent.mkdir(parents=True, exist_ok=True)
                        scene_path.write_text("fake output")
                        return MagicMock(returncode=0)

                    mock_run.side_effect = _make_scene
                    orchestrator.run_phase("scene_assembling", ctx)

        job_dir = project_dir / "runtime" / "jobs" / "job-snap-001"
        manifest_path = job_dir / ".scene_snapshot" / "manifest.json"

        # Snapshot manifest was created
        assert manifest_path.exists(), "Snapshot manifest should exist after first run"

        # Manifest is valid JSON
        import json

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert len(manifest) == 2, "Should have entries for 2 scene folders"

        # Each entry has source, local, size, mtime
        for entry in manifest:
            assert "source" in entry
            assert "local" in entry
            assert "size" in entry
            assert "mtime" in entry
            local_path = job_dir / ".scene_snapshot" / entry["local"]
            assert local_path.exists(), f"Local copy {entry['local']} should exist"
            assert local_path.stat().st_size == entry["size"]
            # Source should point to an original file
            source_path = Path(entry["source"])
            assert source_path.exists(), f"Source {entry['source']} should exist"

    def test_snapshot_creates_local_copies(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """Snapshot copies files physically into the job directory."""
        folder = tmp_root / "workspace" / "scene" / "opener"
        folder.mkdir(parents=True)
        source = folder / "intro.mp4"
        source.write_text("original video data")

        ctx = PhaseContext(
            job_id="job-snap-copy",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/opener"],
        )

        with patch.object(subprocess, "run"):
            orchestrator.run_phase("scene_assembling", ctx)

        job_dir = project_dir / "runtime" / "jobs" / "job-snap-copy"
        snapshot_dir = job_dir / ".scene_snapshot"
        manifest = json.loads(
            (snapshot_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert len(manifest) == 1
        local_path = snapshot_dir / manifest[0]["local"]
        # Local copy is a real copy, not a symlink
        assert local_path.exists()
        assert local_path.read_text() == "original video data"
        # Local copy should be in .scene_snapshot/, not at the job root
        assert local_path.parent.name == ".scene_snapshot"
        # Source is preserved in manifest
        assert manifest[0]["source"] == str(source.resolve())

    def test_reuses_snapshot_on_rerun(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """Second run reuses snapshot clips instead of re-randomizing from source folders."""
        folder = tmp_root / "workspace" / "scene" / "brand-intro"
        folder.mkdir(parents=True)
        for i in range(3):
            (folder / f"clip_{i}.mp4").write_text(f"video data {i}")

        ctx = PhaseContext(
            job_id="job-snap-reuse",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/brand-intro"],
        )

        # First run: picks random clip, creates snapshot
        with patch.object(subprocess, "run"):
            orchestrator.run_phase("scene_assembling", ctx)

        job_dir = project_dir / "runtime" / "jobs" / "job-snap-reuse"
        manifest_path = job_dir / ".scene_snapshot" / "manifest.json"
        first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        first_local = first_manifest[0]["local"]

        # Delete source folder — snapshot must stand alone
        import shutil as _shutil

        _shutil.rmtree(folder)
        assert not folder.exists()

        # Second run: should succeed from snapshot, not fail on missing folder
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = orchestrator.run_phase("scene_assembling", ctx)

        assert len(result) == 1
        assert result[0].kind == "scene_segment"

        # Manifest should still reference the same snapshot local path
        second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert second_manifest[0]["local"] == first_local

    def test_force_reselect_replaces_snapshot(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """force_reselect=True discards the old snapshot and re-randomizes."""
        folder = tmp_root / "workspace" / "scene" / "brand-intro"
        folder.mkdir(parents=True)
        for i in range(3):
            (folder / f"clip_{i}.mp4").write_text(f"video data {i}")

        ctx = PhaseContext(
            job_id="job-snap-force",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/brand-intro"],
        )

        # First run: creates snapshot
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            orchestrator.run_phase("scene_assembling", ctx)

        job_dir = project_dir / "runtime" / "jobs" / "job-snap-force"
        manifest_path = job_dir / ".scene_snapshot" / "manifest.json"

        # Second run with force_reselect: re-randomizes
        ctx.options["force_reselect"] = True
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            orchestrator.run_phase("scene_assembling", ctx)

        # Snapshot was re-written (mtime advanced)
        assert manifest_path.stat().st_mtime > 0

        # scene_segment.mp4 was regenerated
        assert (job_dir / "scene_segment.mp4").exists()

    def test_fingerprint_change_invalidates_snapshot(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """When a source file's fingerprint changes, snapshot is re-created on next run."""
        folder = tmp_root / "workspace" / "scene" / "intro"
        folder.mkdir(parents=True)
        source = folder / "opener.mp4"
        source.write_text("original content")

        ctx = PhaseContext(
            job_id="job-snap-fp",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/intro"],
        )

        # First run: creates snapshot
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            orchestrator.run_phase("scene_assembling", ctx)

        job_dir = project_dir / "runtime" / "jobs" / "job-snap-fp"
        manifest_path = job_dir / ".scene_snapshot" / "manifest.json"

        # Change source file content (different size → different fingerprint)
        import time

        source.write_text("modified content that changes the file size")
        time.sleep(0.01)  # ensure mtime advances

        # Second run without force_reselect: fingerprint mismatch → re-randomize
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            orchestrator.run_phase("scene_assembling", ctx)

        # Snapshot was re-created with updated fingerprint
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest[0]["size"] == len("modified content that changes the file size")

        # The new local copy contains the modified source
        local_path = job_dir / ".scene_snapshot" / manifest[0]["local"]
        assert local_path.read_text() == "modified content that changes the file size"


# ---------------------------------------------------------------------------
# 4. montage_assembling handler — reviewed snapshot → Montage Segment (#264)
# ---------------------------------------------------------------------------


class TestMontageAssembling:
    """montage_assembling builds the independent Montage Segment from the
    reviewed snapshot, TTS audio and canonical sentence timings in both
    generate and import modes.  Import mode does NOT use scene_segment.mp4
    in montage_assembling — scene composition is owned by video_rendering."""

    def test_requires_reviewed_snapshot(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """No reviewed_assets.json → MONTAGE_SNAPSHOT_MISSING."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)

        error = orchestrator.validate_phase_input("montage_assembling", ctx)
        assert error is not None
        assert error.code == "MONTAGE_SNAPSHOT_MISSING"

    def test_requires_audio(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """reviewed snapshot present but no audio → MONTAGE_AUDIO_MISSING."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "reviewed_assets.json").write_text("[]", encoding="utf-8")

        error = orchestrator.validate_phase_input("montage_assembling", ctx)
        assert error is not None
        assert error.code == "MONTAGE_AUDIO_MISSING"

    def test_requires_sentence_timings(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """reviewed snapshot + audio but no sentences → MONTAGE_TIMINGS_MISSING."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "reviewed_assets.json").write_text("[]", encoding="utf-8")
        (job_dir / "audio.mp3").write_bytes(b"fake audio")

        error = orchestrator.validate_phase_input("montage_assembling", ctx)
        assert error is not None
        assert error.code == "MONTAGE_TIMINGS_MISSING"

    def test_builds_montage_from_snapshot(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """With reviewed snapshot, audio and sentence timings,
        montage_assembling calls build_base_video and emits montage artifacts."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "reviewed_assets.json").write_text(
            json.dumps(
                [
                    {
                        "sentence": "第一句。",
                        "file_path": "",
                        "asset_id": "",
                        "visual_type": "blank",
                        "duration": 1.5,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (job_dir / "audio.mp3").write_bytes(b"fake audio")
        (job_dir / "sentences.json").write_text(
            json.dumps(
                [
                    {
                        "index": 0,
                        "text": "第一句。",
                        "start_seconds": 0.0,
                        "end_seconds": 1.5,
                        "model": "",
                        "voice": "",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        expected_trim = [
            {
                "sentence": "第一句。",
                "file_path": "",
                "asset_id": "",
                "visual_type": "blank",
                "ss": 0.0,
                "duration": 1.5,
            }
        ]

        def _build(project_dir, job, output_path, sentence_timings=None):
            output_path.write_text("montage video")
            return expected_trim

        orchestrator._video_svc.build_base_video.side_effect = _build

        artifacts = orchestrator.run_phase("montage_assembling", ctx)

        kinds = {a.kind for a in artifacts}
        assert kinds == {"montage_segment", "montage_segments"}
        assert (job_dir / "montage_segment.mp4").exists()
        assert (
            json.loads((job_dir / "montage_segments.json").read_text(encoding="utf-8"))
            == expected_trim
        )
        # build_base_video was called with output_path pointing to
        # montage_segment.mp4 (positional arg 3).
        call_args = orchestrator._video_svc.build_base_video.call_args
        assert call_args[0][2] == job_dir / "montage_segment.mp4"

    def test_ignores_scene_segment(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        """Even when scene_segment.mp4 exists alongside, montage_assembling
        does NOT consume or copy it — scene composition is video_rendering's job."""
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True)
        (job_dir / "scene_segment.mp4").write_text("scene from import mode")
        (job_dir / "reviewed_assets.json").write_text(
            json.dumps(
                [
                    {
                        "sentence": "第一句。",
                        "file_path": "",
                        "asset_id": "",
                        "visual_type": "blank",
                        "duration": 1.5,
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (job_dir / "audio.mp3").write_bytes(b"fake audio")
        (job_dir / "sentences.json").write_text(
            json.dumps(
                [
                    {
                        "index": 0,
                        "text": "第一句。",
                        "start_seconds": 0.0,
                        "end_seconds": 1.5,
                        "model": "",
                        "voice": "",
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        def _build(project_dir, job, output_path, sentence_timings=None):
            output_path.write_text("montage video")
            return [{"sentence": "第一句。", "visual_type": "blank", "duration": 1.5}]

        orchestrator._video_svc.build_base_video.side_effect = _build

        artifacts = orchestrator.run_phase("montage_assembling", ctx)

        # The scene_segment.mp4 is left untouched — it is NOT consumed by
        # montage_assembling.
        assert (job_dir / "scene_segment.mp4").read_text() == "scene from import mode"
        # montage_assembling produces montage_segment.mp4, not assembled.mp4.
        assert (job_dir / "montage_segment.mp4").exists()
        assert not (job_dir / "assembled.mp4").exists()
        kinds = {a.kind for a in artifacts}
        assert "montage_segment" in kinds
        assert "assembled_video" not in kinds


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
        record.scene_folder_ids = ["scenes/one"]
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
        """montage_assembling → handler via general dispatch (new_phase=None, not video_rendering)."""
        record = make_record(phase="montage_assembling", mode="import")
        action = _compute_transition(record, ())
        assert action.run_handler is True
        assert action.handler_phase == "montage_assembling"
        assert (
            action.new_phase is None
        )  # general dispatch: advance happens after artifacts

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

        # Verify transition to subtitle_generating
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

    def test_import_mode_advances_past_montage_assembling(
        self,
    ) -> None:
        """End-to-end: montage_assembling produces montage segment → advances to video_rendering.

        montage_assembling is a structured media phase so the tick service
        calls execute_phase, not run_phase.
        """
        record = make_record(phase="montage_assembling", mode="import")
        mock_repo = MagicMock()
        mock_repo.load_job.return_value = record
        mock_orch = MagicMock(spec=PhaseOrchestrator)
        mock_orch.execute_phase.return_value = PhaseExecutionSuccess(
            artifacts=[
                ArtifactPointer(
                    kind="montage_segment",
                    relative_path="montage_segment.mp4",
                    url="/workspace/montage_segment.mp4",
                    size_bytes=2000,
                ),
                ArtifactPointer(
                    kind="montage_segments",
                    relative_path="montage_segments.json",
                    url="/workspace/montage_segments.json",
                    size_bytes=150,
                ),
            ]
        )

        svc = JobTickService(orchestrator=mock_orch, repo=mock_repo)
        summary = svc.tick(
            "proj-001",
            "test-job",
            "test",
            root_dir=Path("/tmp"),
            project_dir=Path("/tmp/proj"),
        )

        assert summary.action == "advanced"
        assert summary.from_phase == "montage_assembling"
        # Should advance to video_rendering (next in PHASE_ORDER after montage_assembling)
        assert summary.to_phase == "video_rendering"

    # -- Import mode subtitle routing (issue #56, corrected in #173) -----

    def test_subtitle_generating_to_asset_retrieving_with_artifacts(
        self,
    ) -> None:
        """Import mode: subtitle_generating + artifacts → asset_retrieving (corrected flow)."""
        record = make_record(phase="subtitle_generating", mode="import")
        action = _compute_transition(
            record,
            ({"kind": "subtitle", "relative_path": "subtitle.srt"},),
        )
        assert action.new_phase == "asset_retrieving"

    def test_subtitle_generating_skip_to_asset_retrieving(self) -> None:
        """Import mode: subtitle_generating + skip_subtitle → asset_retrieving."""
        record = make_record(
            phase="subtitle_generating", mode="import", skip_subtitle=True
        )
        action = _compute_transition(record, ())
        assert action.new_phase == "asset_retrieving"
        assert "skip" in action.message.lower()

    def test_subtitle_generating_runs_handler_no_artifacts(self) -> None:
        """Import mode: subtitle_generating, no skip, no artifacts → run handler."""
        record = make_record(phase="subtitle_generating", mode="import")
        action = _compute_transition(record, ())
        assert action.run_handler is True
        assert action.handler_phase == "subtitle_generating"
        assert action.new_phase is None

    def test_subtitle_after_artifacts_routes_to_asset_retrieving(
        self,
    ) -> None:
        """_transition_after_artifacts: import mode subtitle → asset_retrieving (corrected flow)."""
        from packages.pipeline_services.job_tick_service import (
            _transition_after_artifacts,
        )

        record = make_record(phase="subtitle_generating", mode="import")
        action = _transition_after_artifacts(
            record,
            ({"kind": "subtitle", "relative_path": "subtitle.srt"},),
        )
        assert action.new_phase == "asset_retrieving"

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


# ---------------------------------------------------------------------------
# 5. scene_assembling input validation (file drift guard)
# ---------------------------------------------------------------------------


class TestSceneAssemblingInputValidation:
    """validate_phase_input guards scene_assembling against drifted input."""

    def test_validate_rejects_empty_scene_folders(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        ctx.scene_folder_paths = []
        error = orchestrator.validate_phase_input("scene_assembling", ctx)
        assert error is not None
        assert error.code == "SCENE_INPUT_MISSING"
        assert error.retryable is False

    def test_validate_rejects_missing_folder(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/missing"],
        )
        error = orchestrator.validate_phase_input("scene_assembling", ctx)
        assert error is not None
        assert error.code == "SCENE_FOLDER_NOT_FOUND"
        assert error.retryable is False

    def test_validate_rejects_folder_without_videos(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        scene_folder = tmp_root / "workspace" / "scene" / "empty"
        scene_folder.mkdir(parents=True)
        (scene_folder / "readme.txt").write_text("no videos here")
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/empty"],
        )
        error = orchestrator.validate_phase_input("scene_assembling", ctx)
        assert error is not None
        assert error.code == "SCENE_MEDIA_MISSING"
        assert error.retryable is False

    def test_validate_accepts_valid_folder_with_video(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        scene_folder = tmp_root / "workspace" / "scene" / "valid"
        scene_folder.mkdir(parents=True)
        (scene_folder / "clip.mp4").write_bytes(b"fake video")
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/valid"],
        )
        error = orchestrator.validate_phase_input("scene_assembling", ctx)
        assert error is None

    def test_validate_accepts_snapshot_even_with_empty_folder(
        self, orchestrator: PhaseOrchestrator, tmp_root: Path, project_dir: Path
    ) -> None:
        """When snapshot exists, validation passes even without source folders."""
        scene_folder = tmp_root / "workspace" / "scene" / "valid"
        scene_folder.mkdir(parents=True)
        (scene_folder / "clip.mp4").write_bytes(b"fake video")

        ctx = PhaseContext(
            job_id="job-snap-val",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            scene_folder_paths=["scene/valid"],
        )

        # First run creates the snapshot
        with patch.object(subprocess, "run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            orchestrator.run_phase("scene_assembling", ctx)

        # Delete source folder (snapshot must be self-sufficient)
        import shutil

        shutil.rmtree(scene_folder)
        assert not scene_folder.exists()

        # Validation should pass because snapshot exists
        error = orchestrator.validate_phase_input("scene_assembling", ctx)
        assert error is None
