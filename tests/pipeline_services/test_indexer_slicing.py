"""Tests for video slicing in AssetIndexer.

Following TDD: These tests verify that video slices are valid and can be concatenated.
The current implementation using -c copy will fail these tests because slices
may not start with keyframes.
"""

import subprocess
from pathlib import Path

import pytest

from packages.pipeline_services.asset_library.indexer import AssetIndexer
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.media_utils import _resolve_ffprobe_path


def _create_test_video(
    output_path: Path, duration: float = 20.0, keyframe_interval: int = 240
) -> Path:
    """Create a test video with infrequent keyframes to trigger the slicing bug.

    keyframe_interval: frames between keyframes (default 240 = 10 seconds at 24fps)
    """
    # 使用项目根目录的绝对路径
    project_root = Path(__file__).parent.parent.parent
    ffmpeg = project_root / "tools" / "bin" / "ffmpeg.exe"
    if not ffmpeg.exists():
        ffmpeg = "ffmpeg"
    cmd = [
        str(ffmpeg),
        "-f",
        "lavfi",
        "-i",
        f"color=c=red:s=320x240:d={duration}:r=24",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-g",
        str(keyframe_interval),
        "-keyint_min",
        str(keyframe_interval),
        "-sc_threshold",
        "0",
        "-y",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path


def _concat_videos(
    ffmpeg_path: str, video_paths: list[Path], output_path: Path
) -> bool:
    """Attempt to concatenate videos. Returns True if successful, False if error."""
    concat_list = output_path.parent / "concat_list.txt"
    with open(concat_list, "w") as f:
        for vp in video_paths:
            f.write(f"file '{vp}'\n")

    cmd = [
        str(ffmpeg_path),
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        "-y",
        str(output_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=60,
        )
        return result.returncode == 0
    except subprocess.CalledProcessError:
        return False
    finally:
        concat_list.unlink(missing_ok=True)


def _get_first_frame_type(ffmpeg_path: str, video_path: Path) -> str | None:
    """Get the type of the first video frame (I, P, B) using ffprobe.

    Returns 'I' for keyframes, 'P' for predicted frames, 'B' for bidirectional, or None on error.
    """
    ffprobe_path = _resolve_ffprobe_path()
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "frame=pict_type",
        "-of",
        "csv",
        "-read_intervals",
        "%+0.01",
        str(video_path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30,
        )
        if result.returncode == 0 and result.stdout:
            # Parse first line: "frame,I," or "frame,P,"
            parts = result.stdout.strip().split(",")
            if len(parts) >= 2:
                return parts[1]
        return None
    except Exception:
        return None


@pytest.mark.slow
class TestIndexerSlicing:
    """Test that video slicing produces valid, concatenatable slices."""

    def test_slices_can_be_concatenated(self, tmp_path):
        """
        RED TEST: This test should FAIL with current implementation using -c copy.

        The bug: _scene_detect_and_cut uses -c copy which doesn't ensure slices
        start with keyframes. This causes concat to fail with:
        [h264] No start code is found.
        [h264] Error splitting the input into NAL units.
        """
        # Arrange
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        repo = AssetRepository(db_path)

        # 使用项目根目录的绝对路径
        project_root = Path(__file__).parent.parent.parent
        ffmpeg_path = project_root / "tools" / "bin" / "ffmpeg.exe"
        if not ffmpeg_path.exists():
            ffmpeg_path = "ffmpeg"

        # Create a test video with infrequent keyframes (every 10 seconds)
        # This causes slicing at 8-second intervals to not align with keyframes
        test_video = source_dir / "test_video.mp4"
        _create_test_video(test_video, duration=20.0, keyframe_interval=240)

        # Create indexer
        indexer = AssetIndexer(
            ffmpeg_path=str(ffmpeg_path),
            repository=repo,
        )

        # Act - slice the video
        slices = indexer._scene_detect_and_cut(test_video, output_dir)

        # Assert - we should get multiple slices
        assert len(slices) > 1, f"Expected multiple slices, got {len(slices)}"

        # Assert - each slice should start with a keyframe (I-frame)
        for slice_path in slices:
            assert slice_path.exists(), f"Slice {slice_path} does not exist"
            first_frame = _get_first_frame_type(str(ffmpeg_path), slice_path)
            assert first_frame == "I", (
                f"Slice {slice_path} starts with {first_frame}-frame, not I-frame (keyframe)"
            )

        # Critical test - slices should be concatenatable
        concat_output = tmp_path / "concat_result.mp4"
        can_concat = _concat_videos(str(ffmpeg_path), slices, concat_output)
        assert can_concat, (
            "FAILED: Slices cannot be concatenated! This is the bug - slices don't start with keyframes."
        )

    def test_long_clip_split_produces_valid_slices(self, tmp_path):
        """
        RED TEST: This test should FAIL with current implementation.

        Tests the _split_long_clip function specifically.
        """
        # Arrange
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        db_path = tmp_path / "test.db"
        repo = AssetRepository(db_path)

        # 使用项目根目录的绝对路径
        project_root = Path(__file__).parent.parent.parent
        ffmpeg_path = project_root / "tools" / "bin" / "ffmpeg.exe"
        if not ffmpeg_path.exists():
            ffmpeg_path = "ffmpeg"

        # Create a video that's longer than SPLIT_CLIP_SECONDS (5s)
        long_clip = tmp_path / "long_clip.mp4"
        _create_test_video(long_clip, duration=12.0)

        indexer = AssetIndexer(
            ffmpeg_path=str(ffmpeg_path),
            repository=repo,
        )

        # Act - split the long clip
        sub_clips = indexer._split_long_clip(long_clip, output_dir)

        # Assert
        assert len(sub_clips) > 1, f"Expected multiple sub-clips, got {len(sub_clips)}"

        # Critical test - sub-clips should be concatenatable
        concat_output = tmp_path / "concat_sub_result.mp4"
        can_concat = _concat_videos(str(ffmpeg_path), sub_clips, concat_output)
        assert can_concat, "FAILED: Sub-clips cannot be concatenated! This is the bug."
