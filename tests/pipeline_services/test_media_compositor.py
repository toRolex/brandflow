"""Tests for MediaCompositor — ffmpeg composition primitives."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch


from packages.pipeline_services.media_compositor import MediaCompositor


class TestConcatTwo:
    """concat_two normalizes and concatenates two video inputs."""

    @patch("packages.pipeline_services.media_compositor.get_ffmpeg_path")
    @patch("packages.pipeline_services.media_compositor.subprocess.run")
    def test_filter_complex_contains_normalize_and_concat(
        self, mock_run: MagicMock, mock_ffmpeg: MagicMock, tmp_path: Path
    ) -> None:
        mock_ffmpeg.return_value = "ffmpeg"
        mock_run.return_value = MagicMock(returncode=0)

        first = tmp_path / "first.mp4"
        second = tmp_path / "second.mp4"
        out = tmp_path / "out.mp4"
        first.write_text("fake")
        second.write_text("fake")

        result = MediaCompositor.concat_two(first, second, out)

        assert result == out
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-filter_complex" in call_args
        filter_idx = call_args.index("-filter_complex")
        filter_str = call_args[filter_idx + 1]
        assert "concat=n=2" in filter_str
        assert "scale=720:1280" in filter_str
        assert "fps=30" in filter_str
        assert "format=pix_fmts=yuv420p" in filter_str
        assert "setsar=1" in filter_str
        assert "-c:v" in call_args
        assert "libx264" in call_args
        assert "-preset" in call_args
        assert "ultrafast" in call_args
        assert "-crf" in call_args
        assert "23" in call_args
        assert "-pix_fmt" in call_args
        assert "yuv420p" in call_args
        assert "+faststart" in call_args


class TestCrossfadeScene:
    """crossfade_scene chains xfade transitions across multiple clips."""

    @patch("packages.pipeline_services.media_compositor.get_ffmpeg_path")
    @patch("packages.pipeline_services.media_compositor.get_media_duration")
    @patch("packages.pipeline_services.media_compositor.subprocess.run")
    def test_filter_complex_contains_xfade_chain(
        self,
        mock_run: MagicMock,
        mock_duration: MagicMock,
        mock_ffmpeg: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_ffmpeg.return_value = "ffmpeg"
        mock_duration.return_value = 5.0
        mock_run.return_value = MagicMock(returncode=0)

        clips = [tmp_path / f"clip{i}.mp4" for i in range(3)]
        for c in clips:
            c.write_text("fake")
        out = tmp_path / "scene.mp4"

        result = MediaCompositor.crossfade_scene(clips, out, transition_duration=0.5)

        assert result == out
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "ffmpeg"
        assert "-filter_complex" in call_args
        filter_idx = call_args.index("-filter_complex")
        filter_str = call_args[filter_idx + 1]
        assert "xfade=transition=fade:duration=0.500:offset=4.500" in filter_str
        assert "xfade=transition=fade:duration=0.500:offset=9.000" in filter_str
        assert "concat" not in filter_str
        assert "-c:v" in call_args
        assert "libx264" in call_args
        assert "-preset" in call_args
        assert "ultrafast" in call_args
        assert "-crf" in call_args
        assert "23" in call_args
        assert "-pix_fmt" in call_args
        assert "yuv420p" in call_args
        assert "+faststart" in call_args

    @patch("packages.pipeline_services.media_compositor.get_ffmpeg_path")
    @patch("packages.pipeline_services.media_compositor.get_media_duration")
    @patch("packages.pipeline_services.media_compositor.subprocess.run")
    def test_single_clip_copies_directly(
        self,
        mock_run: MagicMock,
        mock_duration: MagicMock,
        mock_ffmpeg: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_ffmpeg.return_value = "ffmpeg"
        mock_duration.return_value = 5.0

        clip = tmp_path / "only.mp4"
        clip.write_text("fake scene")
        out = tmp_path / "scene.mp4"

        result = MediaCompositor.crossfade_scene([clip], out, transition_duration=0.5)

        assert result == out
        assert out.exists()
        assert out.read_text() == "fake scene"
        mock_run.assert_not_called()
