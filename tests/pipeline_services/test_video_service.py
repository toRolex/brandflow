from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.pipeline_services.video_service import (
    VideoService,
    _render_cover_title_png,
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
        assert "-filter_complex" in call_args
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


class TestCoverTitlePng:
    def test_render_with_highlight(self, tmp_path):
        out = tmp_path / "cover.png"
        result = _render_cover_title_png(
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
            output_path=out,
        )
        assert result.exists()
        assert result.stat().st_size > 0

    def test_render_no_highlights(self, tmp_path):
        out = tmp_path / "simple.png"
        result = _render_cover_title_png(
            text="简单标题",
            highlight_words=[],
            style={},
            video_width=1080,
            video_height=1920,
            output_path=out,
        )
        assert result.exists()

    def test_render_top_position(self, tmp_path):
        out = tmp_path / "top.png"
        result = _render_cover_title_png(
            text="标题",
            highlight_words=[],
            style={"position": "top"},
            video_width=1080,
            video_height=1920,
            output_path=out,
        )
        assert result.exists()


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

        # cover_title.png should exist
        png_path = tmp_path / "cover_title.png"
        assert png_path.exists()
        assert png_path.stat().st_size > 0

        # overlay filter should be in the FFmpeg command
        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        assert "overlay" in joined

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


class TestVideoServiceMusicMix:
    """Tests for burn_final_video with background music mixing."""

    def _make_service(self):
        return VideoService(dry_run=False)

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.get_media_duration", return_value=10.0)
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_with_music_includes_amix_afade_and_stream_loop(
        self, mock_run, mock_duration, mock_ffmpeg, tmp_path
    ):
        """Background music path triggers amix + afade + stream_loop in FFmpeg command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        music = tmp_path / "bgm.mp3"
        final = tmp_path / "final.mp4"
        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")
        music.write_bytes(b"fake")

        svc = self._make_service()
        svc.burn_final_video(base, audio, None, final, music_path=music, music_volume=80)

        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        assert "-stream_loop" in call_args
        assert str(music) in call_args
        assert "amix" in joined
        assert "afade=t=out" in joined

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.get_media_duration", return_value=10.0)
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_with_music_volume_scaled(
        self, mock_run, mock_duration, mock_ffmpeg, tmp_path
    ):
        """music_volume parameter is reflected as FFmpeg volume factor."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        music = tmp_path / "bgm.mp3"
        final = tmp_path / "final.mp4"
        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")
        music.write_bytes(b"fake")

        svc = self._make_service()
        svc.burn_final_video(base, audio, None, final, music_path=music, music_volume=50)

        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        assert "amix=inputs=2" in joined
        # music volume factor should be 0.50
        assert "volume=0.50" in joined or "volume=0.5" in joined

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.get_media_duration", return_value=10.0)
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_with_music_default_fade_duration(
        self, mock_run, mock_duration, mock_ffmpeg, tmp_path
    ):
        """Fade-out duration defaults to 1.5s ending at voice duration."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        music = tmp_path / "bgm.mp3"
        final = tmp_path / "final.mp4"
        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")
        music.write_bytes(b"fake")

        svc = self._make_service()
        svc.burn_final_video(base, audio, None, final, music_path=music)

        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        # fade starts at voice_duration - 1.5 = 8.5, with d=1.5
        assert "afade=t=out:st=8.500:d=1.5" in joined

    @patch("packages.pipeline_services.video_service.get_ffmpeg_path", return_value="ffmpeg")
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_burn_without_music_no_amix(
        self, mock_run, mock_ffmpeg, tmp_path
    ):
        """No music_path means no amix/afade/stream_loop in the command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        final = tmp_path / "final.mp4"
        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")

        svc = self._make_service()
        svc.burn_final_video(base, audio, None, final)

        call_args = mock_run.call_args[0][0]
        joined = " ".join(call_args)
        assert "amix" not in joined
        assert "afade" not in joined

    def test_dry_run_burn_with_music_does_not_fail(self, tmp_path):
        """Dry run with music_path writes stub and does not fail."""
        svc = VideoService(dry_run=True)
        base = tmp_path / "base.mp4"
        audio = tmp_path / "audio.mp3"
        music = tmp_path / "bgm.mp3"
        final = tmp_path / "final.mp4"
        base.write_bytes(b"fake")
        audio.write_bytes(b"fake")
        music.write_bytes(b"fake")

        svc.burn_final_video(base, audio, None, final, music_path=music)
        assert final.exists()
