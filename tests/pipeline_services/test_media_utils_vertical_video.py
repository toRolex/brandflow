from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest
from PIL import Image

from packages.pipeline_services.media_utils import (
    TARGET_VIDEO_HEIGHT,
    TARGET_VIDEO_WIDTH,
    assemble_vertical_base_video,
    normalize_clip_to_vertical,
)


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or os.environ.get("FFMPEG_PATH", "ffmpeg")


def _ffprobe() -> str:
    return shutil.which("ffprobe") or os.environ.get("FFPROBE_PATH", "ffprobe")


def _make_color_video(output_path: Path, size: str, duration: float = 1.0, color: str = "red") -> Path:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={size}:d={duration}:r=24",
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


def _probe_size(video_path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            _ffprobe(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0:s=x",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    width, height = result.stdout.strip().split("x")
    return int(width), int(height)


def _probe_duration(video_path: Path) -> float:
    result = subprocess.run(
        [
            _ffprobe(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def _extract_first_frame(video_path: Path, frame_path: Path) -> Path:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(frame_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return frame_path


@pytest.mark.slow
def test_normalize_clip_to_vertical_outputs_1080x1920(tmp_path: Path) -> None:
    source = _make_color_video(tmp_path / "landscape.mp4", "1280x720", duration=1.5)
    output = tmp_path / "normalized.mp4"

    normalize_clip_to_vertical(_ffmpeg(), source, output)

    assert output.exists()
    assert _probe_size(output) == (TARGET_VIDEO_WIDTH, TARGET_VIDEO_HEIGHT)


@pytest.mark.slow
def test_normalize_clip_to_vertical_uses_non_black_background(tmp_path: Path) -> None:
    source = _make_color_video(tmp_path / "landscape.mp4", "1280x720", duration=1.5, color="red")
    output = tmp_path / "normalized.mp4"
    frame = tmp_path / "frame.png"

    normalize_clip_to_vertical(_ffmpeg(), source, output)
    _extract_first_frame(output, frame)

    with Image.open(frame) as image:
        pixel = cast(tuple[int, int, int], image.convert("RGB").getpixel((0, 0)))
        assert pixel != (0, 0, 0)


@pytest.mark.slow
def test_assemble_vertical_base_video_handles_mixed_orientations(tmp_path: Path) -> None:
    clips = [
        _make_color_video(tmp_path / "landscape.mp4", "1280x720", duration=1.0, color="red"),
        _make_color_video(tmp_path / "square.mp4", "640x640", duration=1.0, color="green"),
        _make_color_video(tmp_path / "portrait.mp4", "720x1280", duration=1.0, color="blue"),
    ]
    output = tmp_path / "base.mp4"

    assemble_vertical_base_video(_ffmpeg(), clips, audio_duration=3.0, output_path=output)

    assert output.exists()
    assert _probe_size(output) == (TARGET_VIDEO_WIDTH, TARGET_VIDEO_HEIGHT)


@pytest.mark.slow
def test_assemble_vertical_base_video_respects_audio_duration(tmp_path: Path) -> None:
    clips = [
        _make_color_video(tmp_path / "clip_a.mp4", "1280x720", duration=1.0, color="red"),
        _make_color_video(tmp_path / "clip_b.mp4", "640x640", duration=1.0, color="green"),
    ]
    output = tmp_path / "base.mp4"
    audio_duration = 5.0

    assemble_vertical_base_video(_ffmpeg(), clips, audio_duration=audio_duration, output_path=output)

    assert output.exists()
    assert math.isclose(_probe_duration(output), audio_duration, abs_tol=0.3)


@pytest.mark.slow
def test_assemble_vertical_base_video_applies_recipe_filter_without_changing_resolution(tmp_path: Path) -> None:
    clips = [_make_color_video(tmp_path / "clip.mp4", "1280x720", duration=1.0, color="red")]
    output = tmp_path / "base.mp4"

    assemble_vertical_base_video(
        _ffmpeg(),
        clips,
        audio_duration=2.0,
        output_path=output,
        recipe_filter="eq=brightness=0.01:contrast=1.02:saturation=1.05",
    )

    assert output.exists()
    assert _probe_size(output) == (TARGET_VIDEO_WIDTH, TARGET_VIDEO_HEIGHT)


@pytest.mark.slow
def test_empty_clips_raise_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        assemble_vertical_base_video(_ffmpeg(), [], audio_duration=5.0, output_path=tmp_path / "base.mp4")
