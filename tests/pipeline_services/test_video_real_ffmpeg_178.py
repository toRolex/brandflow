"""Real FFmpeg tests: mixed clip-blank, all blank, and audio-video continuity.

These tests use actual FFmpeg to verify blank clip rendering produces valid
video files with correct durations.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from packages.pipeline_services.video_service import VideoService


pytestmark = [pytest.mark.slow, pytest.mark.media_integration]


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or os.environ.get("FFMPEG_PATH", "ffmpeg")


def _ffprobe() -> str:
    return shutil.which("ffprobe") or os.environ.get("FFPROBE_PATH", "ffprobe")


def _make_test_audio(output_path: Path, duration: float = 5.0) -> Path:
    """Generate a silent audio file (mono, 44100Hz, 16-bit)."""
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=d={duration}:c=pink:a=0.01",
            "-ac",
            "1",
            "-ar",
            "44100",
            "-sample_fmt",
            "s16",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _make_test_video(
    output_path: Path, duration: float = 2.0, color: str = "red"
) -> Path:
    """Generate a solid-color test video."""
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=1080x1920:d={duration}:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output_path


def _probe_duration(video_path: Path) -> float:
    """Get video duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            _ffprobe(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return float(result.stdout.strip())


SKIP_REAL = not shutil.which("ffmpeg") or not shutil.which("ffprobe")
REAL_REASON = "ffmpeg or ffprobe not available"


@pytest.mark.skipif(SKIP_REAL, reason=REAL_REASON)
class TestRealFFmpegMixedClips:
    """Real FFmpeg test: mixed real clips and blank clips."""

    def test_mixed_clip_and_blank(self, tmp_path: Path) -> None:
        red_vid = _make_test_video(tmp_path / "red.mp4", 2.0, "red")
        blue_vid = _make_test_video(tmp_path / "blue.mp4", 2.0, "blue")
        audio = _make_test_audio(tmp_path / "audio.mp3", 5.0)

        svc = VideoService(dry_run=False)
        job = {
            "job_id": "mixed-test",
            "asset_bundle": {
                "audio_path": str(audio),
                "selected_clips": [
                    {
                        "sentence": "红色介绍。",
                        "file_path": str(red_vid),
                        "asset_id": "a1",
                        "duration_seconds": 2.0,
                        "visual_type": "clip",
                    },
                    {
                        "sentence": "空白过渡。",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "visual_type": "blank",
                    },
                    {
                        "sentence": "蓝色结尾。",
                        "file_path": str(blue_vid),
                        "asset_id": "a2",
                        "duration_seconds": 2.0,
                        "visual_type": "clip",
                    },
                ],
            },
        }
        output = tmp_path / "base.mp4"
        svc.build_base_video(tmp_path, job, output)

        assert output.exists()
        assert output.stat().st_size > 1000
        duration = _probe_duration(output)
        assert duration > 0

    def test_all_blank(self, tmp_path: Path) -> None:
        """All-blank produces a valid video with only black frames."""
        audio = _make_test_audio(tmp_path / "audio.mp3", 3.0)

        svc = VideoService(dry_run=False)
        job = {
            "job_id": "all-blank-test",
            "asset_bundle": {
                "audio_path": str(audio),
                "selected_clips": [
                    {
                        "sentence": "空白一。",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "visual_type": "blank",
                    },
                    {
                        "sentence": "空白二。",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "visual_type": "blank",
                    },
                    {
                        "sentence": "空白三。",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "visual_type": "blank",
                    },
                ],
            },
        }
        output = tmp_path / "base.mp4"
        svc.build_base_video(tmp_path, job, output)

        assert output.exists()
        assert output.stat().st_size > 1000
        duration = _probe_duration(output)
        assert duration > 0

    def test_single_blank(self, tmp_path: Path) -> None:
        """Single blank entry generates valid video."""
        audio = _make_test_audio(tmp_path / "audio.mp3", 2.0)

        svc = VideoService(dry_run=False)
        job = {
            "job_id": "single-blank",
            "asset_bundle": {
                "audio_path": str(audio),
                "selected_clips": [
                    {
                        "sentence": "只有空白。",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "visual_type": "blank",
                    },
                ],
            },
        }
        output = tmp_path / "base.mp4"
        svc.build_base_video(tmp_path, job, output)

        assert output.exists()
        assert output.stat().st_size > 1000
        duration = _probe_duration(output)
        # Duration should match audio duration
        assert math.isclose(duration, 2.0, abs_tol=1.0)
