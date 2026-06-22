from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.pipeline_services.video_service import (
    VideoService,
    _build_ass_for_cover_title,
    _hex_to_ass_bgr,
    _ass_escape,
)


class TestVideoService:
    def _make_service(self):
        return VideoService(dry_run=False)

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.get_media_duration", return_value=10.0)
    @patch("packages.pipeline_services.video_service.get_video_size", return_value=(1080, 1920))
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_build_base_video_calls_ffmpeg(self, mock_run, mock_size, mock_duration, mock_ffmpeg, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        clip_dir = tmp_path / "clips"
        clip_dir.mkdir()
        (clip_dir / "clip1.mp4").write_bytes(b"fake")

        job = {
            "job_id": "test-001",
            "asset_bundle": {
                "audio_path": str(tmp_path / "audio.mp3"),
                "selected_clips": [
                    {"file_path": str(clip_dir / "clip1.mp4"), "start": 0.0, "end": 3.0, "duration_seconds": 5.0}
                ],
            },
        }
        (tmp_path / "audio.mp3").write_bytes(b"fake")
        output = tmp_path / "base.mp4"

        svc = self._make_service()
        svc.build_base_video(tmp_path, job, output)

        assert mock_run.called

    def test_dry_run_writes_stub(self, tmp_path):
        svc = VideoService(dry_run=True)
        job = {"job_id": "test-002", "asset_bundle": {"audio_path": str(tmp_path / "audio.mp3"), "selected_clips": []}}
        output = tmp_path / "base.mp4"
        (tmp_path / "audio.mp3").write_bytes(b"fake")
        svc.build_base_video(tmp_path, job, output)
        assert output.exists()

    def test_build_base_video_raises_on_missing_audio(self, tmp_path):
        svc = self._make_service()
        job = {
            "job_id": "test-003",
            "asset_bundle": {"audio_path": str(tmp_path / "missing.mp3"), "selected_clips": []},
        }
        output = tmp_path / "base.mp4"
        with pytest.raises(FileNotFoundError):
            svc.build_base_video(tmp_path, job, output)

    def test_dry_run_burn_writes_stub(self, tmp_path):
        svc = VideoService(dry_run=True)
        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        srt = tmp_path / "subs.srt"
        final = tmp_path / "final.mp4"

        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")
        srt.write_bytes(b"1\n00:00:00,000 --> 00:00:03,000\nTest\n")

        svc.burn_final_video(base, audio, srt, final)
        assert final.exists()

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.get_video_size", return_value=(1080, 1920))
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_final_video_with_cover(self, mock_run, mock_size, mock_ffmpeg, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        srt = tmp_path / "subs.srt"
        cover = tmp_path / "cover.mp4"
        final = tmp_path / "final.mp4"

        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")
        srt.write_bytes(b"1\n00:00:00,000 --> 00:00:03,000\nTest\n")
        cover.write_bytes(b"fake")

        svc = self._make_service()
        svc.burn_final_video(base, audio, srt, final, cover)

        assert mock_run.called
        # cover path uses filter_complex with concat
        call_args = mock_run.call_args[0][0]
        assert "-filter_complex" in call_args

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_final_video_without_cover(self, mock_run, mock_ffmpeg, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        srt = tmp_path / "subs.srt"
        final = tmp_path / "final.mp4"

        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")
        srt.write_bytes(b"1\n00:00:00,000 --> 00:00:03,000\nTest\n")

        svc = self._make_service()
        svc.burn_final_video(base, audio, srt, final)

        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "-vf" in call_args
        assert "subtitles" in " ".join(call_args)

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_final_video_no_subtitles(self, mock_run, mock_ffmpeg, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        final = tmp_path / "final.mp4"

        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")

        svc = self._make_service()
        svc.burn_final_video(base, audio, None, final)

        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        assert "-vf" not in joined
        assert "subtitles" not in joined


class TestCoverTitleAss:
    def test_hex_to_ass_bgr(self):
        assert _hex_to_ass_bgr("#FFD700") == "&H0000D7FF&"
        assert _hex_to_ass_bgr("#000000") == "&H00000000&"
        assert _hex_to_ass_bgr("#FF0000") == "&H000000FF&"
        assert _hex_to_ass_bgr("FFD700") == "&H0000D7FF&"

    def test_ass_escape(self):
        assert _ass_escape("hello") == "hello"
        assert _ass_escape(r"C:\path") == r"C:\\path"
        assert _ass_escape("{text}") == r"\{text\}"

    def test_build_ass_structure(self, tmp_path):
        ass_path = _build_ass_for_cover_title(
            text="鲜嫩荔枝菌",
            highlight_words=["荔枝菌"],
            style={
                "primary_color": "#FFD700",
                "outline_color": "#000000",
                "highlight_color": "#FF0000",
                "outline_width": 2.0,
                "position": "center",
            },
            video_width=1080,
            video_height=1920,
            duration=3.0,
            output_path=tmp_path / "cover.ass",
        )
        assert ass_path.exists()
        content = ass_path.read_text(encoding="utf-8")

        # Verify key ASS sections
        assert "[Script Info]" in content
        assert "PlayResX: 1080" in content
        assert "PlayResY: 1920" in content
        assert "[V4+ Styles]" in content
        assert "Style: Default" in content
        assert "[Events]" in content
        assert "Dialogue:" in content

        # Verify highlight color override
        assert r"{\c&H000000FF&}" in content
        assert "荔枝菌" in content

        # Verify duration range
        assert "0:00:00.00,0:00:03.00" in content

    def test_build_ass_top_position(self, tmp_path):
        ass_path = _build_ass_for_cover_title(
            text="标题",
            highlight_words=[],
            style={"position": "top"},
            video_width=1080,
            video_height=1920,
            output_path=tmp_path / "top.ass",
        )
        content = ass_path.read_text(encoding="utf-8")
        # Alignment 8 = top-center. The Format line declares the columns,
        # and the Style line provides values in order — verify the event exists.
        assert "0:00:00.00,0:00:03.00" in content
        assert "标题" in content

    def test_build_ass_bottom_position(self, tmp_path):
        ass_path = _build_ass_for_cover_title(
            text="标题",
            highlight_words=[],
            style={"position": "bottom"},
            video_width=1080,
            video_height=1920,
            output_path=tmp_path / "bottom.ass",
        )
        content = ass_path.read_text(encoding="utf-8")
        assert "0:00:00.00,0:00:03.00" in content

    def test_build_ass_no_highlights(self, tmp_path):
        ass_path = _build_ass_for_cover_title(
            text="简单标题",
            highlight_words=[],
            style={},
            video_width=1080,
            video_height=1920,
            output_path=tmp_path / "simple.ass",
        )
        content = ass_path.read_text(encoding="utf-8")
        # No highlight overrides
        assert r"{\c" not in content

    def test_build_ass_default_output_path(self, tmp_path):
        """Default output_path writes to cover_title.ass in cwd."""
        import os
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            ass_path = _build_ass_for_cover_title(
                text="测试",
                highlight_words=[],
                style={},
                video_width=1080,
                video_height=1920,
            )
            assert ass_path.exists()
            assert ass_path.name == "cover_title.ass"
        finally:
            os.chdir(orig_cwd)


class TestVideoServiceCoverTitle:
    """Tests for burn_final_video with cover_title dict."""

    def _make_service(self):
        return VideoService(dry_run=False)

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.get_media_duration", return_value=10.0)
    @patch("packages.pipeline_services.video_service.get_video_size", return_value=(1080, 1920))
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_with_cover_title_short_video_skips(
        self, mock_run, mock_size, mock_duration, mock_ffmpeg, tmp_path
    ):
        """Video shorter than 3s skips cover title ASS generation."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        mock_duration.return_value = 2.0  # < 3s

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        final = tmp_path / "final.mp4"
        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")

        cover_title = {
            "text": "标题",
            "highlight_words": ["题"],
            "style": {"position": "center"},
        }

        svc = self._make_service()
        svc.burn_final_video(base, audio, None, final, cover_title=cover_title)

        # ASS file should NOT exist (skipped)
        ass_path = tmp_path / "cover_title.ass"
        assert not ass_path.exists()

        # No subtitles filter in command
        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        assert "subtitles" not in joined

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.get_media_duration", return_value=10.0)
    @patch("packages.pipeline_services.video_service.get_video_size", return_value=(1080, 1920))
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_with_cover_title_generates_ass_and_subtitles_filter(
        self, mock_run, mock_size, mock_duration, mock_ffmpeg, tmp_path
    ):
        """Video >= 3s generates ASS and applies subtitles filter."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        final = tmp_path / "final.mp4"
        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")

        cover_title = {
            "text": "鲜嫩荔枝菌",
            "highlight_words": ["荔枝菌"],
            "style": {
                "primary_color": "#FFD700",
                "outline_color": "#000000",
                "highlight_color": "#FF0000",
                "outline_width": 2.0,
                "position": "center",
            },
        }

        svc = self._make_service()
        svc.burn_final_video(base, audio, None, final, cover_title=cover_title)

        # ASS file should exist with cover title content
        ass_path = tmp_path / "cover_title.ass"
        assert ass_path.exists()
        content = ass_path.read_text(encoding="utf-8")
        # Highlight words get wrapped in ASS color override tags,
        # so the full text "鲜嫩荔枝菌" is split. Check parts.
        assert "鲜嫩" in content
        assert "荔枝菌" in content
        assert r"{\c" in content  # color override for highlight

        # subtitles filter should be in the FFmpeg command
        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        assert "subtitles" in joined
        # Cover title ASS uses force_style
        assert "force_style" in joined

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.get_media_duration", return_value=10.0)
    @patch("packages.pipeline_services.video_service.get_video_size", return_value=(1080, 1920))
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_with_cover_title_empty_text_skips(
        self, mock_run, mock_size, mock_duration, mock_ffmpeg, tmp_path
    ):
        """Empty cover_title text skips ASS generation entirely."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        final = tmp_path / "final.mp4"
        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")

        svc = self._make_service()
        svc.burn_final_video(base, audio, None, final, cover_title={"text": "", "highlight_words": [], "style": {}})

        ass_path = tmp_path / "cover_title.ass"
        assert not ass_path.exists()

        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        assert "subtitles" not in joined
