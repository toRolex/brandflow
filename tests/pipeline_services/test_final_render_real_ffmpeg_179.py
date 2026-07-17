"""Real-FFmpeg end-to-end tests for AV alignment + Final Timeline (issue #179).

These tests run the actual ``video_rendering`` → ``final_rendering`` pipeline
with real FFmpeg to verify the TTS/subtitle offset lands on the montage start
and the final duration is correct for both the scene and no-scene paths
(acceptance criteria 3 and 8).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from packages.pipeline_services.media_utils import get_media_duration
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
)
from packages.pipeline_services.subtitle_service import SubtitleService
from packages.pipeline_services.video_service import VideoService


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _make_video(output: Path, duration: float, color: str) -> Path:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=720x1280:d={duration}:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _make_audio(output: Path, duration: float, freq: int = 440) -> Path:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:duration={duration}",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _audio_start_ms(audio_path: Path) -> float:
    """Detect the first non-silent moment (ms) via ffmpeg silencedetect."""
    result = subprocess.run(
        [
            _ffmpeg(),
            "-i",
            str(audio_path),
            "-af",
            "silencedetect=noise=-30dB:d=0.05",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    # First "silence_end" marks the onset of sound.
    for line in result.stderr.splitlines():
        if "silence_end" in line:
            # e.g. "silence_end: 2.041 | ..."
            token = line.split("silence_end:")[1].split("|")[0].strip()
            return float(token) * 1000.0
    return 0.0


SKIP_REAL = not shutil.which("ffmpeg") or not shutil.which("ffprobe")
REAL_REASON = "ffmpeg or ffprobe not available"


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def project_dir(tmp_root: Path) -> Path:
    d = tmp_root / "workspace" / "projects" / "proj-001"
    d.mkdir(parents=True)
    return d


def _orchestrator() -> PhaseOrchestrator:
    return PhaseOrchestrator(
        subtitle_svc=SubtitleService(),
        video_svc=VideoService(dry_run=False),
        schedule_store=MagicMock(),
    )


def _write_montage_inputs(job_dir: Path, tts_path: Path, clip_path: Path) -> None:
    """Write audio.mp3, selected_clips.json and subtitles.srt for the montage."""
    shutil.copy2(tts_path, job_dir / "audio.mp3")
    (job_dir / "selected_clips.json").write_text(
        json.dumps(
            [
                {
                    "sentence": "第一句介绍产品。",
                    "file_path": str(clip_path),
                    "asset_id": "a1",
                    "duration_seconds": 5.0,
                    "visual_type": "clip",
                }
            ]
        ),
        encoding="utf-8",
    )
    (job_dir / "subtitles.srt").write_text(
        "1\n00:00:00,000 --> 00:00:03,000\n第一句介绍产品。\n", encoding="utf-8"
    )


@pytest.mark.skipif(SKIP_REAL, reason=REAL_REASON)
class TestRealRenderWithScene:
    """Scene path: TTS offset to montage start, final duration = scene+montage."""

    def test_final_duration_and_tts_offset(self, tmp_root, project_dir) -> None:
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        job_dir.mkdir(parents=True, exist_ok=True)
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            options={},
        )

        # scene = 2s red, montage clip = 5s blue (trimmed to ~3s), tts = 3s tone
        scene_src = _make_video(job_dir / "_scene_src.mp4", 2.0, "red")
        clip_src = _make_video(job_dir / "_clip_src.mp4", 5.0, "blue")
        tts = _make_audio(job_dir / "_tts.wav", 3.0)
        # assembled.mp4 is the scene segment used by video_rendering
        shutil.copy2(scene_src, job_dir / "assembled.mp4")
        _write_montage_inputs(job_dir, tts, clip_src)

        orch = _orchestrator()

        # video_rendering: build base + inject alignment + timeline
        orch.run_phase("video_rendering", ctx)
        assert (job_dir / "base.mp4").exists()
        assert (job_dir / "audio_aligned.mp3").exists()
        assert (job_dir / "subtitles_offset.srt").exists()
        timeline = json.loads((job_dir / "final_timeline.json").read_text("utf-8"))
        assert timeline["aligned"] is True

        # base video duration = scene(2) + montage(~3) ≈ 5s
        base_ms = get_media_duration(job_dir / "base.mp4") * 1000
        assert base_ms == pytest.approx(5000, abs=600)

        # final_rendering: burn aligned audio + offset srt
        artifacts = orch.run_phase("final_rendering", ctx)
        final_path = job_dir / "final.mp4"
        assert final_path.exists()
        assert any(a.kind == "final_video" for a in artifacts)

        # final duration ≈ scene + montage (not truncated by -shortest)
        final_ms = get_media_duration(final_path) * 1000
        assert final_ms == pytest.approx(5000, abs=700)

        # TTS onset ≈ scene duration (2000ms), not 0
        onset = _audio_start_ms(final_path)
        assert onset == pytest.approx(2000, abs=400)

        # timeline montage segment starts at scene_ms (~2000)
        montage = [s for s in timeline["segments"] if s["kind"] == "montage"]
        assert montage[0]["start_ms"] == timeline["segments"][0]["end_ms"]
        assert timeline["segments"][0]["kind"] == "scene"
        assert montage[0]["start_ms"] == pytest.approx(2000, abs=50)


@pytest.mark.skipif(SKIP_REAL, reason=REAL_REASON)
class TestRealRenderNoScene:
    """No-scene path: offset is identity, final duration ≈ montage duration."""

    def test_final_duration_matches_montage(self, tmp_root, project_dir) -> None:
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        job_dir.mkdir(parents=True, exist_ok=True)
        ctx = PhaseContext(
            job_id="job-001",
            project_dir=project_dir,
            root_dir=tmp_root,
            product="test",
            options={},
        )

        clip_src = _make_video(job_dir / "_clip_src.mp4", 5.0, "blue")
        tts = _make_audio(job_dir / "_tts.wav", 3.0)
        _write_montage_inputs(job_dir, tts, clip_src)
        # no assembled.mp4 → scene_ms = 0

        orch = _orchestrator()
        orch.run_phase("video_rendering", ctx)
        timeline = json.loads((job_dir / "final_timeline.json").read_text("utf-8"))
        # no scene segment; montage starts at 0
        assert all(s["kind"] != "scene" for s in timeline["segments"])
        assert timeline["segments"][0]["start_ms"] == 0

        orch.run_phase("final_rendering", ctx)
        final_path = job_dir / "final.mp4"
        assert final_path.exists()

        # final duration ≈ montage (~3s); TTS starts at ~0
        final_ms = get_media_duration(final_path) * 1000
        assert final_ms == pytest.approx(3000, abs=700)
        onset = _audio_start_ms(final_path)
        assert onset < 400
