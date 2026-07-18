"""Tests: VideoService handles blank (black frame) and mixed clips."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from packages.pipeline_services.video_service import VideoService


class TestVideoServiceBlankClip:
    def _make_service(self):
        return VideoService(dry_run=False)

    @patch(
        "packages.pipeline_services.video_service.get_ffmpeg_path",
        return_value="ffmpeg",
    )
    @patch(
        "packages.pipeline_services.video_service.get_media_duration", return_value=10.0
    )
    @patch(
        "packages.pipeline_services.video_service.get_video_size",
        return_value=(1080, 1920),
    )
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_build_base_video_with_blank_clip(
        self, mock_run, mock_size, mock_duration, mock_ffmpeg, tmp_path
    ):
        """Blank clip generates a black color frame instead of trimming a real file."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake")

        job = {
            "job_id": "test-blank",
            "asset_bundle": {
                "audio_path": str(audio_path),
                "selected_clips": [
                    {
                        "sentence": "空白句。",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "visual_type": "blank",
                    }
                ],
            },
        }
        output = tmp_path / "base.mp4"
        svc = self._make_service()
        svc.build_base_video(tmp_path, job, output)

        # ffmpeg was called at least once (for color source or blank generation)
        assert mock_run.called
        # Check that color=black appears for the blank clip
        all_calls = [c[0][0] for c in mock_run.call_args_list]
        found_black = any(
            "black" in str(args) or "color" in str(args) for args in all_calls
        )
        assert found_black, "Blank clip should trigger color source ffmpeg call"

    @patch(
        "packages.pipeline_services.video_service.get_ffmpeg_path",
        return_value="ffmpeg",
    )
    @patch(
        "packages.pipeline_services.video_service.get_media_duration", return_value=10.0
    )
    @patch(
        "packages.pipeline_services.video_service.get_video_size",
        return_value=(1080, 1920),
    )
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_build_base_video_with_mixed_blank_and_real(
        self, mock_run, mock_size, mock_duration, mock_ffmpeg, tmp_path
    ):
        """Mixed blank + real clips: blank gets color=black, real gets trim from source."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        clip_dir = tmp_path / "clips"
        clip_dir.mkdir()
        (clip_dir / "real.mp4").write_bytes(b"fake_video")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake")

        job = {
            "job_id": "test-mixed",
            "asset_bundle": {
                "audio_path": str(audio_path),
                "selected_clips": [
                    {
                        "sentence": "第一句介绍。",
                        "file_path": str(clip_dir / "real.mp4"),
                        "asset_id": "a1",
                        "duration_seconds": 5.0,
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
                        "sentence": "第三句结尾。",
                        "file_path": str(clip_dir / "real.mp4"),
                        "asset_id": "a3",
                        "duration_seconds": 3.0,
                        "visual_type": "clip",
                    },
                ],
            },
        }
        output = tmp_path / "base.mp4"
        svc = self._make_service()
        svc.build_base_video(tmp_path, job, output)

        assert mock_run.called
        # At least one call should have color=black
        all_calls_str = [str(c[0][0]) for c in mock_run.call_args_list]
        found_black = any("black" in s or "color" in s for s in all_calls_str)
        found_real = any("real.mp4" in s for s in all_calls_str)
        assert found_black, "Should have color=black for blank clip"
        assert found_real, "Should have reference to real clip file"

    def test_dry_run_with_blank_clip(self, tmp_path):
        """Dry run with blank clips writes stub without failing."""
        svc = VideoService(dry_run=True)
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake")

        job = {
            "job_id": "test-dry-blank",
            "asset_bundle": {
                "audio_path": str(audio_path),
                "selected_clips": [
                    {"sentence": "空白。", "visual_type": "blank"},
                    {"sentence": "也空白。", "visual_type": "blank"},
                ],
            },
        }
        output = tmp_path / "base.mp4"
        svc.build_base_video(tmp_path, job, output)
        assert output.exists()

    def test_dry_run_preserves_asset_ids(self, tmp_path):
        """Dry run should track asset_ids from all clip entries."""
        svc = VideoService(dry_run=True)
        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake")

        job = {
            "job_id": "test-asset-ids",
            "asset_bundle": {
                "audio_path": str(audio_path),
                "selected_clips": [
                    {
                        "sentence": "A",
                        "file_path": "/a.mp4",
                        "asset_id": "a1",
                        "visual_type": "clip",
                    },
                    {
                        "sentence": "B",
                        "file_path": "",
                        "asset_id": "",
                        "visual_type": "blank",
                    },
                ],
            },
        }
        output = tmp_path / "base.mp4"
        svc.build_base_video(tmp_path, job, output)
        assert job.get("used_asset_ids") == ["a1"]

    @patch(
        "packages.pipeline_services.video_service.get_ffmpeg_path",
        return_value="ffmpeg",
    )
    @patch(
        "packages.pipeline_services.video_service.get_media_duration", return_value=10.0
    )
    @patch(
        "packages.pipeline_services.video_service.get_video_size",
        return_value=(1080, 1920),
    )
    @patch("packages.pipeline_services.video_service.subprocess.run")
    def test_blank_clip_uses_sentence_timing(
        self, mock_run, mock_size, mock_duration, mock_ffmpeg, tmp_path
    ):
        """Blank clip with sentence_timings uses per-sentence duration instead of uniform split.

        Spec #178 AC-5: blank 时长只取后端 Sentence Timing。
        """
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        clip_dir = tmp_path / "clips"
        clip_dir.mkdir()
        (clip_dir / "a.mp4").write_bytes(b"fake")

        audio_path = tmp_path / "audio.mp3"
        audio_path.write_bytes(b"fake")

        job = {
            "job_id": "test-blank-timing",
            "asset_bundle": {
                "audio_path": str(audio_path),
                "selected_clips": [
                    {
                        "sentence": "第一句介绍。",
                        "file_path": str(clip_dir / "a.mp4"),
                        "asset_id": "a1",
                        "duration_seconds": 10.0,
                        "visual_type": "clip",
                    },
                    {
                        "sentence": "空白中段。",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "visual_type": "blank",
                    },
                    {
                        "sentence": "最后收尾。",
                        "file_path": str(clip_dir / "a.mp4"),
                        "asset_id": "a2",
                        "duration_seconds": 10.0,
                        "visual_type": "clip",
                    },
                ],
            },
        }

        # Sentence timings: blank should be exactly 2.5s, not uniform 10/3 ≈ 3.33s
        sentence_timings = [
            {
                "index": 0,
                "text": "第一句介绍。",
                "start_seconds": 0.0,
                "end_seconds": 4.0,
            },
            {
                "index": 1,
                "text": "空白中段。",
                "start_seconds": 4.0,
                "end_seconds": 6.5,
            },
            {
                "index": 2,
                "text": "最后收尾。",
                "start_seconds": 6.5,
                "end_seconds": 10.0,
            },
        ]

        output = tmp_path / "base.mp4"
        svc = self._make_service()
        result = svc.build_base_video(
            tmp_path, job, output, sentence_timings=sentence_timings
        )

        # Blank segment (index 1) should be ~2.5s from sentence timing
        blank_param = result[1]
        blank_duration = blank_param["duration"]
        assert abs(blank_duration - 2.5) < 0.01, (
            f"Blank duration should be 2.5s from sentence timing, got {blank_duration}"
        )

        # Non-blank segments get uniform split plus rebalance from blank's surplus
        # The blank consumed 2.5s of 10s total, leaving 7.5s for 2 non-blank clips
        assert abs(result[0]["duration"] + result[2]["duration"] - 7.5) < 0.2
