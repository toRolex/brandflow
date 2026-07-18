"""Tests for Phase 2 Slice 5 — Export Bundle ZIP packaging.

Covers:
- Full export bundle creation with all artifacts present
- timeline.json generation (scene clips, montage clips, audio, subtitle)
- Missing file handling (no subtitles, no selected_clips.json)
- Edge case: empty job directory
- On-demand API endpoint behaviour
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from packages.pipeline_services.export_service import (
    _add_audio_to_zip,
    _add_source_clips_to_zip,
    build_export_bundle,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def workspace_dir(tmp_root: Path) -> Path:
    d = tmp_root / "workspace"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture()
def project_dir(workspace_dir: Path) -> Path:
    d = workspace_dir / "projects" / "proj-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def job_dir(project_dir: Path) -> Path:
    d = project_dir / "runtime" / "jobs" / "job-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def export_dir(project_dir: Path) -> Path:
    return project_dir / "runtime" / "exports"


def _write_minimal_final_timeline(job_dir: Path) -> None:
    """Write an empty-segments Final Timeline so export passes the re-render guard.

    Empty segments make ``segment_final_video`` a no-op (no ffmpeg call), which
    keeps these ZIP-structure tests free of a real-FFmpeg dependency; the real
    segmentation behaviour is covered by test_segment_export_181.py.
    """
    (job_dir / "final_timeline.json").write_text(
        json.dumps(
            {
                "version": "1.0",
                "duration_ms": 0,
                "aligned": True,
                "fingerprint": "minimal",
                "segments": [],
            }
        ),
        encoding="utf-8",
    )


def _populate_full_job(job_dir: Path, workspace_dir: Path) -> None:
    """Create a complete set of job artifacts for testing."""
    # final.mp4
    (job_dir / "final.mp4").write_text("final video data")

    # authoritative render-time Final Timeline (required for export since #181)
    _write_minimal_final_timeline(job_dir)

    # audio.mp3 (no wav — tests mp3->wav rename)
    (job_dir / "audio.mp3").write_text("audio data")

    # subtitles.srt
    (job_dir / "subtitles.srt").write_text(
        "1\n00:00:01,000 --> 00:00:05,000\nHello world\n"
    )

    # selected_clips.json
    clips_dir = workspace_dir / "shared_assets" / "source"
    clips_dir.mkdir(parents=True)
    for i in range(2):
        (clips_dir / f"clip_{i}.mp4").write_text(f"montage clip {i}")

    selected = [
        {
            "sentence": "Sentence one",
            "category": "产地溯源",
            "file_path": str(clips_dir / "clip_0.mp4"),
            "duration_seconds": 3.0,
        },
        {
            "sentence": "Sentence two",
            "category": "切配处理",
            "file_path": str(clips_dir / "clip_1.mp4"),
            "duration_seconds": 4.0,
        },
    ]
    (job_dir / "selected_clips.json").write_text(
        json.dumps(selected, ensure_ascii=False)
    )

    # Scene folders (via workspace /scene)
    for folder_name in ("brand-intro", "product-show"):
        folder = workspace_dir / "scene" / folder_name
        folder.mkdir(parents=True)
        (folder / "intro.mp4").write_text(f"scene clip {folder_name}")


_SCENE_CFG_FULL = {
    "folders": [
        {"name": "brand-intro", "path": "scene/brand-intro"},
        {"name": "product-show", "path": "scene/product-show"},
    ],
    "transition_duration_ms": 500,
}


# ---------------------------------------------------------------------------
# build_export_bundle — ZIP structure
# ---------------------------------------------------------------------------


class TestBuildExportBundle:
    def test_full_bundle_structure(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, export_dir: Path
    ) -> None:
        """Full job artifacts produce complete ZIP with expected directories."""
        _populate_full_job(job_dir, workspace_dir)

        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: _SCENE_CFG_FULL,
        )

        assert zip_path.exists()
        assert zip_path.name == "export_job-001.zip"

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        prefix = "export_job-001/"
        # Check expected entries exist
        assert f"{prefix}final/final.mp4" in names
        assert f"{prefix}audio/tts.wav" in names
        assert f"{prefix}subtitle/script.srt" in names
        assert f"{prefix}timeline.json" in names
        # Scene clips
        assert any("source_clips/scene_" in n for n in names), (
            f"no scene clip in {names}"
        )
        # Montage clips
        assert any("source_clips/montage_" in n for n in names), (
            f"no montage clip in {names}"
        )

    def test_bundle_without_subtitles(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, export_dir: Path
    ) -> None:
        """Missing subtitles.srt -> no subtitle/ directory in ZIP."""
        _populate_full_job(job_dir, workspace_dir)
        (job_dir / "subtitles.srt").unlink()

        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: _SCENE_CFG_FULL,
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            prefix = "export_job-001/"
            assert f"{prefix}subtitle/script.srt" not in names
            # Timeline should not have subtitle field
            timeline_data = json.loads(zf.read(f"{prefix}timeline.json"))
            assert "subtitle" not in timeline_data

    def test_bundle_without_selected_clips(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, export_dir: Path
    ) -> None:
        """Missing selected_clips.json -> no montage clips in ZIP."""
        _populate_full_job(job_dir, workspace_dir)
        (job_dir / "selected_clips.json").unlink()

        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: _SCENE_CFG_FULL,
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        montage_clips = [n for n in names if "montage_" in n]
        assert montage_clips == [], f"unexpected montage clips: {montage_clips}"

    def test_bundle_empty_job_dir(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, export_dir: Path
    ) -> None:
        """Empty job directory produces a ZIP with only timeline.json."""
        _write_minimal_final_timeline(job_dir)
        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: _SCENE_CFG_FULL,
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        prefix = "export_job-001/"
        assert f"{prefix}final/final.mp4" not in names
        assert f"{prefix}audio/tts.wav" not in names
        assert f"{prefix}timeline.json" in names

    def test_audio_mp3_renamed_to_wav(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, export_dir: Path
    ) -> None:
        """MP3 audio is stored as tts.wav in the ZIP."""
        (job_dir / "audio.mp3").write_text("mp3 data")
        _write_minimal_final_timeline(job_dir)

        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: _SCENE_CFG_FULL,
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            prefix = "export_job-001/"
            assert f"{prefix}audio/tts.wav" in names
            assert zf.read(f"{prefix}audio/tts.wav") == b"mp3 data"

    def test_audio_wav_preferred(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, export_dir: Path
    ) -> None:
        """When both exist, audio.wav is preferred over audio.mp3."""
        (job_dir / "audio.wav").write_text("wav data")
        (job_dir / "audio.mp3").write_text("mp3 data")
        _write_minimal_final_timeline(job_dir)

        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: _SCENE_CFG_FULL,
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            assert zf.read("export_job-001/audio/tts.wav") == b"wav data"

    def test_bundle_creates_export_dir(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, tmp_path: Path
    ) -> None:
        """Export directory is created if it does not exist."""
        export_dir = project_dir / "runtime" / "exports"
        assert not export_dir.exists()
        _write_minimal_final_timeline(job_dir)

        build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: _SCENE_CFG_FULL,
        )

        assert export_dir.exists()

    def test_bundle_clips_from_scene_folders(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, export_dir: Path
    ) -> None:
        """Scene clips are enumerated from configured scene folders."""
        for name in ("intro", "hero"):
            folder = workspace_dir / "scene" / name
            folder.mkdir(parents=True)
            (folder / f"{name}_clip.mp4").write_text("scene data")

        scene_config = {
            "folders": [
                {"name": "intro", "path": "scene/intro"},
                {"name": "hero", "path": "scene/hero"},
            ],
            "transition_duration_ms": 500,
        }

        _write_minimal_final_timeline(job_dir)
        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: scene_config,
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        scene_clips = [n for n in names if "source_clips/scene_" in n]
        assert len(scene_clips) == 2, f"expected 2 scene clips, got {scene_clips}"

    def test_bundle_scene_clips_skips_missing_folders(
        self, job_dir: Path, workspace_dir: Path, project_dir: Path, export_dir: Path
    ) -> None:
        """Missing scene folders are gracefully skipped."""
        scene_config = {
            "folders": [
                {"name": "missing", "path": "scene/missing"},
            ],
            "transition_duration_ms": 500,
        }

        _write_minimal_final_timeline(job_dir)
        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: scene_config,
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        scene_clips = [n for n in names if "source_clips/scene_" in n]
        assert scene_clips == []


# ---------------------------------------------------------------------------
# generate_timeline_json — removed (replaced by segment_export.build_timeline_2)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestAddAudioToZip:
    def test_adds_wav(self, job_dir: Path, tmp_path: Path) -> None:
        """WAV audio is added as tts.wav."""
        (job_dir / "audio.wav").write_text("wav")
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            _add_audio_to_zip(job_dir, zf, "")

        with zipfile.ZipFile(zip_path, "r") as zf:
            assert zf.read("audio/tts.wav") == b"wav"

    def test_adds_mp3_as_wav(self, job_dir: Path, tmp_path: Path) -> None:
        """MP3 is stored as tts.wav when no WAV file exists."""
        (job_dir / "audio.mp3").write_text("mp3")
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            _add_audio_to_zip(job_dir, zf, "")

        with zipfile.ZipFile(zip_path, "r") as zf:
            assert zf.read("audio/tts.wav") == b"mp3"

    def test_skips_when_no_audio(self, job_dir: Path, tmp_path: Path) -> None:
        """No audio files -> nothing added."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            _add_audio_to_zip(job_dir, zf, "")

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        assert names == []


class TestAddSourceClipsToZip:
    def test_scene_clips_added_from_config(
        self, job_dir: Path, workspace_dir: Path, tmp_path: Path
    ) -> None:
        """Scene clips from config folders are added with scene_ prefix."""
        folder = workspace_dir / "scene" / "brand-intro"
        folder.mkdir(parents=True)
        (folder / "clip.mp4").write_text("data")

        scene_config = {
            "folders": [{"name": "brand-intro", "path": "scene/brand-intro"}],
            "transition_duration_ms": 500,
        }

        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            _add_source_clips_to_zip(job_dir, workspace_dir, zf, "", scene_config)

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        assert any("scene_" in n for n in names)

    def test_montage_clips_from_selected_json(
        self, job_dir: Path, workspace_dir: Path, tmp_path: Path
    ) -> None:
        """Montage clips from selected_clips.json are added with montage_ prefix."""
        clip_dir = workspace_dir / "shared_assets" / "source"
        clip_dir.mkdir(parents=True)
        (clip_dir / "asset.mp4").write_text("asset data")

        selected = [{"file_path": str(clip_dir / "asset.mp4")}]
        (job_dir / "selected_clips.json").write_text(json.dumps(selected))

        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            _add_source_clips_to_zip(job_dir, workspace_dir, zf, "", {})

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()

        assert any("montage_" in n for n in names)
