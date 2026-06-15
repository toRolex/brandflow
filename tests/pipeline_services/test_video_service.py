from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from packages.pipeline_services.video_service import VideoService


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
