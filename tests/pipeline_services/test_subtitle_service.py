from __future__ import annotations

from unittest.mock import patch

from packages.pipeline_services.sentence_tts_service import SentenceTiming
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

        svc.build_srt(
            audio_path, srt_path, "第一句内容。第二句内容。第三句内容。第四句内容。"
        )

        assert srt_path.exists()
        content = srt_path.read_text(encoding="utf-8")
        assert "00:00:00" in content
        assert "-->" in content


class TestSentenceConstrainedSubtitle:
    """Subtitles may split inside a Script Sentence but must never cross one."""

    def _parse_srt_blocks(self, srt_path):
        """Return a list of (index, start_seconds, end_seconds, text)."""
        content = srt_path.read_text(encoding="utf-8-sig", errors="replace")
        blocks = []
        for paragraph in content.strip().split("\n\n"):
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            if len(lines) < 3:
                continue
            index = int(lines[0].lstrip("﻿"))
            timing_line = lines[1]
            text = "\n".join(lines[2:])
            start_str, end_str = timing_line.split(" --> ")
            blocks.append(
                (index, self._to_seconds(start_str), self._to_seconds(end_str), text)
            )
        return blocks

    @staticmethod
    def _to_seconds(timestamp: str) -> float:
        # timestamp format: HH:MM:SS,mmm
        parts = timestamp.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds, millis = parts[2].split(",")
        return hours * 3600 + minutes * 60 + int(seconds) + int(millis) / 1000.0

    @patch("packages.pipeline_services.subtitle_service.get_media_duration")
    @patch("packages.pipeline_services.subtitle_service.detect_silence_points")
    def test_subtitle_chunks_do_not_cross_script_sentence(
        self, mock_silence, mock_duration, tmp_path
    ):
        mock_duration.return_value = 7.0
        mock_silence.return_value = []

        svc = SubtitleService()
        audio_path = tmp_path / "audio.wav"
        audio_path.write_bytes(b"fake")
        srt_path = tmp_path / "subtitles.srt"

        # First sentence is long enough to be split into multiple chunks.
        text = "第一句话的内容比较长一些，需要拆块。第二句短。"
        sentence_timings = [
            SentenceTiming(
                index=0,
                text="第一句话的内容比较长一些，需要拆块。",
                start_seconds=0.0,
                end_seconds=5.0,
            ),
            SentenceTiming(
                index=1, text="第二句短。", start_seconds=5.0, end_seconds=7.0
            ),
        ]

        svc.build_srt(audio_path, srt_path, text, sentence_timings=sentence_timings)

        blocks = self._parse_srt_blocks(srt_path)
        assert len(blocks) >= 2

        first_sentence = svc.clean_script("第一句话的内容比较长一些，需要拆块。")
        second_sentence = svc.clean_script("第二句短。")
        for _idx, start, end, block_text in blocks:
            # Each block must be a substring of exactly one cleaned sentence.
            in_first = block_text in first_sentence
            in_second = block_text in second_sentence
            assert in_first or in_second, (
                f"block not contained in any sentence: {block_text!r}"
            )
            assert not (in_first and in_second), (
                f"block crossed sentence boundary: {block_text!r}"
            )
            if in_first:
                assert start >= 0.0 and end <= 5.0, (
                    f"first-sentence block out of bounds: {start}-{end}"
                )
            else:
                assert start >= 5.0 and end <= 7.0, (
                    f"second-sentence block out of bounds: {start}-{end}"
                )

    @patch("packages.pipeline_services.subtitle_service.get_media_duration")
    @patch("packages.pipeline_services.subtitle_service.detect_silence_points")
    def test_subtitle_uses_sentence_timing_boundaries(
        self, mock_silence, mock_duration, tmp_path
    ):
        mock_duration.return_value = 7.0
        mock_silence.return_value = []

        svc = SubtitleService()
        audio_path = tmp_path / "audio.wav"
        audio_path.write_bytes(b"fake")
        srt_path = tmp_path / "subtitles.srt"

        text = "第一句话的内容比较长一些，需要拆块。第二句短。"
        sentence_timings = [
            SentenceTiming(
                index=0,
                text="第一句话的内容比较长一些，需要拆块。",
                start_seconds=0.0,
                end_seconds=5.0,
            ),
            SentenceTiming(
                index=1, text="第二句短。", start_seconds=5.0, end_seconds=7.0
            ),
        ]

        svc.build_srt(audio_path, srt_path, text, sentence_timings=sentence_timings)

        blocks = self._parse_srt_blocks(srt_path)
        assert blocks

        first_sentence = svc.clean_script("第一句话的内容比较长一些，需要拆块。")
        second_sentence = svc.clean_script("第二句短。")
        for _idx, start, end, block_text in blocks:
            if block_text in first_sentence:
                assert start >= 0.0 and end <= 5.0, (
                    f"first-sentence block out of bounds: {start}-{end}"
                )
            elif block_text in second_sentence:
                assert start >= 5.0 and end <= 7.0, (
                    f"second-sentence block out of bounds: {start}-{end}"
                )
            else:
                raise AssertionError(
                    f"block not contained in any sentence: {block_text!r}"
                )

    @patch("packages.pipeline_services.subtitle_service.get_media_duration")
    @patch("packages.pipeline_services.subtitle_service.detect_silence_points")
    def test_fallback_when_no_sentence_timings(
        self, mock_silence, mock_duration, tmp_path
    ):
        """Without sentence_timings, the legacy behaviour remains unchanged."""
        mock_duration.return_value = 5.0
        mock_silence.return_value = []

        svc = SubtitleService()
        audio_path = tmp_path / "audio.wav"
        audio_path.write_bytes(b"fake")
        srt_path = tmp_path / "subtitles.srt"

        svc.build_srt(audio_path, srt_path, "第一句内容。第二句内容。")

        assert srt_path.exists()
        content = srt_path.read_text(encoding="utf-8")
        assert "-->" in content
