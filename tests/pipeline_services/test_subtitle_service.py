from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from packages.pipeline_services.subtitle_service import SubtitleService


class TestSubtitleService:
    def _make_service(self):
        return SubtitleService()

    def test_split_text_to_chunks(self):
        svc = self._make_service()
        text = "第一句话的内容比较长一些。第二句短。第三句也短。"
        chunks = svc.split_text_to_chunks(text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) >= 10  # SUBTITLE_CHUNK_MIN_CHARS

    def test_subtitle_weight_by_char_count(self):
        svc = self._make_service()
        assert svc.subtitle_weight("一二三四五") > svc.subtitle_weight("一二")
        assert svc.subtitle_weight("一二") > 0

    def test_format_srt_timestamp(self):
        svc = self._make_service()
        assert svc.format_srt_timestamp(0.0) == "00:00:00,000"
        assert svc.format_srt_timestamp(61.5) == "00:01:01,500"
        assert svc.format_srt_timestamp(3661.123) == "01:01:01,123"

    @patch("packages.pipeline_services.subtitle_service.get_media_duration")
    @patch("packages.pipeline_services.subtitle_service.detect_silence_points")
    def test_build_srt_produces_valid_srt(self, mock_silence, mock_duration, tmp_path):
        mock_duration.return_value = 5.0
        mock_silence.return_value = []

        svc = self._make_service()
        audio_path = tmp_path / "test.wav"
        audio_path.write_bytes(b"fake")
        srt_path = tmp_path / "test.srt"

        svc.build_srt(audio_path, srt_path, "第一句内容。第二句内容。第三句内容。第四句内容。")

        assert srt_path.exists()
        content = srt_path.read_text(encoding="utf-8")
        assert "00:00:00" in content
        assert "-->" in content
