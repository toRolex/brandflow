"""Tests for ForceAlignService — forced alignment via whisper-cli + text matching."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from packages.pipeline_services.force_align_service import (
    ForceAlignDiagnostic,
    ForceAlignResult,
    ForceAlignService,
    _normalize,
    _parse_whisper_json,
    _Token,
    _ts_to_ms,
)
from packages.pipeline_services.script_sentence import SentenceTiming


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_whisper_json(
    segments: list[list[tuple[str, float, float]]],
) -> str:
    """Build whisper-cli -oj output JSON from segment/token descriptions.

    Each segment is a list of ``(text, start_ms, end_ms)`` tuples.
    Special tokens like ``[_BEG_]`` are written as-is.
    """
    transcription: list[dict] = []
    for seg_tokens in segments:
        token_objs: list[dict] = []
        for text, start_ms, end_ms in seg_tokens:
            token_objs.append(
                {
                    "text": text,
                    "offsets": {"from": start_ms, "to": end_ms},
                    "timestamps": {
                        "from": _ms_to_ts(start_ms),
                        "to": _ms_to_ts(end_ms),
                    },
                }
            )
        transcription.append({"tokens": token_objs})
    return json.dumps({"transcription": transcription})


def _ms_to_ts(ms: float) -> str:
    h = int(ms // 3600000)
    m = int((ms % 3600000) // 60000)
    s = int((ms % 60000) // 1000)
    millis = int(ms % 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


# ---------------------------------------------------------------------------
# _normalize
# ---------------------------------------------------------------------------


class TestNormalize:
    def test_strips_chinese_punctuation(self) -> None:
        assert _normalize("你好。世界！") == "你好世界"

    def test_strips_whitespace(self) -> None:
        assert _normalize("  hello  world  ") == "helloworld"

    def test_preserves_chinese_characters(self) -> None:
        assert _normalize("今天天气真好") == "今天天气真好"

    def test_preserves_latin_letters(self) -> None:
        assert _normalize("iPhone 14 Pro") == "iphone14pro"

    def test_empty_string(self) -> None:
        assert _normalize("") == ""

    def test_only_punctuation(self) -> None:
        assert _normalize("，。！？") == ""


# ---------------------------------------------------------------------------
# _parse_whisper_json
# ---------------------------------------------------------------------------


class TestParseWhisperJson:
    def test_parses_single_segment_with_tokens(self) -> None:
        json_text = _make_whisper_json(
            [[("今天", 0, 500), ("天气", 500, 1000), ("真好", 1000, 1500)]]
        )
        tokens = _parse_whisper_json(json_text)
        assert len(tokens) == 3
        assert tokens[0].text == "今天"
        assert tokens[0].start_ms == 0
        assert tokens[0].end_ms == 500

    def test_filters_special_tokens(self) -> None:
        json_text = _make_whisper_json(
            [
                [
                    ("[_BEG_]", 0, 0),
                    ("你好", 0, 300),
                    ("[_TT_123]", 300, 300),
                    ("世界", 300, 600),
                ]
            ]
        )
        tokens = _parse_whisper_json(json_text)
        assert len(tokens) == 2
        assert tokens[0].text == "你好"
        assert tokens[1].text == "世界"

    def test_multiple_segments(self) -> None:
        json_text = _make_whisper_json(
            [
                [("第一", 0, 200), ("句", 200, 400)],
                [("第二", 500, 700), ("句", 700, 900)],
            ]
        )
        tokens = _parse_whisper_json(json_text)
        assert len(tokens) == 4

    def test_empty_transcription(self) -> None:
        assert _parse_whisper_json('{"transcription": []}') == []

    def test_invalid_json(self) -> None:
        assert _parse_whisper_json("not json") == []

    def test_parses_timestamps_fallback_when_no_offsets(self) -> None:
        """When offsets are absent, fall back to timestamps string parsing."""
        data = {
            "transcription": [
                {
                    "tokens": [
                        {
                            "text": "测试",
                            "timestamps": {
                                "from": "00:00:01,500",
                                "to": "00:00:02,000",
                            },
                        }
                    ]
                }
            ]
        }
        tokens = _parse_whisper_json(json.dumps(data))
        assert len(tokens) == 1
        assert tokens[0].text == "测试"
        assert tokens[0].start_ms == 1500
        assert tokens[0].end_ms == 2000


# ---------------------------------------------------------------------------
# _ts_to_ms
# ---------------------------------------------------------------------------


class TestTsToMs:
    def test_zero(self) -> None:
        assert _ts_to_ms("00:00:00,000") == 0

    def test_one_second(self) -> None:
        assert _ts_to_ms("00:00:01,000") == 1000

    def test_one_minute(self) -> None:
        assert _ts_to_ms("00:01:00,000") == 60000

    def test_with_millis(self) -> None:
        assert _ts_to_ms("00:00:02,500") == 2500

    def test_colon_separated(self) -> None:
        assert _ts_to_ms("00:00:03:750") == 3750


# ---------------------------------------------------------------------------
# ForceAlignService.align()
# ---------------------------------------------------------------------------


class TestForceAlignServiceAlign:
    """Tests that mock _transcribe so no real whisper-cli is needed."""

    def _make_tokens(self, word_list: list[tuple[str, float, float]]) -> list[_Token]:
        return [_Token(text=t, start_ms=s, end_ms=e) for t, s, e in word_list]

    def test_successful_alignment_all_sentences(self) -> None:
        """Three sentences all match above threshold."""
        tokens = self._make_tokens(
            [
                ("今天", 0, 500),
                ("天气", 500, 1000),
                ("真好", 1000, 1500),
                ("适合", 2000, 2500),
                ("出门", 2500, 3000),
                ("今天", 3500, 4000),
                ("买了", 4000, 4500),
                ("新鞋", 4500, 5000),
            ]
        )
        sentences = ["今天天气真好。", "适合出门。", "今天买了新鞋。"]

        svc = ForceAlignService(confidence_threshold=0.6)
        with patch.object(svc, "_transcribe", return_value=tokens):
            result = svc.align(None, sentences)  # audio_path is not used w/ mock

        assert result.status == "success"
        assert len(result.timings) == 3
        assert all(isinstance(t, SentenceTiming) for t in result.timings)

        # Sentence 0: "今天天气真好" → tokens 0-2, 0-1500 ms
        assert result.timings[0].index == 0
        assert result.timings[0].text == "今天天气真好。"
        assert result.timings[0].start_seconds == pytest.approx(0.0)
        assert result.timings[0].end_seconds == pytest.approx(1.5)
        assert result.timings[0].model == "whisper"
        assert result.timings[0].voice == "upload"

        # Sentence 1: "适合出门" → tokens 3-4, 2000-3000 ms
        assert result.timings[1].start_seconds == pytest.approx(2.0)
        assert result.timings[1].end_seconds == pytest.approx(3.0)

        # Sentence 2: "今天买了新鞋" → tokens 5-7, 3500-5000 ms
        assert result.timings[2].start_seconds == pytest.approx(3.5)
        assert result.timings[2].end_seconds == pytest.approx(5.0)

        assert len(result.diagnostics) == 3
        assert all(d.status == "aligned" for d in result.diagnostics)

    def test_partial_mismatch_some_below_threshold(self) -> None:
        """Sentences 0 and 2 match; sentence 1 is unrelated to audio."""
        tokens = self._make_tokens(
            [
                ("今天", 0, 500),
                ("天气", 500, 1000),
                ("真好", 1000, 1500),
                ("今天", 2000, 2500),
                ("买了", 2500, 3000),
                ("新鞋", 3000, 3500),
            ]
        )
        # Sentence 1 "完全无关的内容" won't match the audio at all
        sentences = ["今天天气真好。", "完全无关的内容。", "今天买了新鞋。"]

        svc = ForceAlignService(confidence_threshold=0.6)
        with patch.object(svc, "_transcribe", return_value=tokens):
            result = svc.align(None, sentences)

        assert result.status == "partial_mismatch"
        assert len(result.timings) == 2  # Only sentences 0 and 2 passed

        # Check diagnostics
        diag_map = {d.sentence_index: d for d in result.diagnostics}
        assert diag_map[0].status == "aligned"
        assert diag_map[1].status == "no_match"
        assert diag_map[2].status == "aligned"

    def test_complete_mismatch_no_sentences_match(self) -> None:
        """Audio content is completely unrelated to script sentences."""
        tokens = self._make_tokens([("你好", 0, 300), ("世界", 300, 600)])
        sentences = ["完全不同的内容。", "毫不相关的文本。"]

        svc = ForceAlignService(confidence_threshold=0.6)
        with patch.object(svc, "_transcribe", return_value=tokens):
            result = svc.align(None, sentences)

        assert result.status == "complete_mismatch"
        assert len(result.timings) == 0
        assert len(result.diagnostics) == 2
        assert all(d.status == "no_match" for d in result.diagnostics)

    def test_empty_sentences_list(self) -> None:
        svc = ForceAlignService()
        with patch.object(svc, "_transcribe", return_value=[]):
            result = svc.align(None, [])
        assert result.status == "complete_mismatch"

    def test_no_tokens_from_whisper(self) -> None:
        svc = ForceAlignService()
        with patch.object(svc, "_transcribe", return_value=[]):
            result = svc.align(None, ["第一句。"])
        assert result.status == "complete_mismatch"
        assert result.diagnostics[0].status == "no_match"

    def test_confidence_threshold_respected(self) -> None:
        """High threshold rejects a match that would pass a lower one."""
        tokens = self._make_tokens(
            [("今天", 0, 300), ("天气", 300, 600), ("不错", 600, 900)]
        )
        sentences = ["今天天气不错。"]

        # Low threshold: matches pass
        svc_loose = ForceAlignService(confidence_threshold=0.6)
        with patch.object(svc_loose, "_transcribe", return_value=tokens):
            result = svc_loose.align(None, sentences)
        assert result.status == "success"
        assert result.diagnostics[0].confidence >= 0.6

        # High threshold: same match may be rejected
        svc_strict = ForceAlignService(confidence_threshold=0.95)
        with patch.object(svc_strict, "_transcribe", return_value=tokens):
            result = svc_strict.align(None, sentences)
        # The perfect match should pass even at 0.95
        assert result.status == "success"
        assert result.diagnostics[0].confidence >= 0.95

    def test_diagnostics_include_audio_range_for_aligned(self) -> None:
        tokens = self._make_tokens([("你好", 0, 500)])
        sentences = ["你好。"]

        svc = ForceAlignService()
        with patch.object(svc, "_transcribe", return_value=tokens):
            result = svc.align(None, sentences)

        assert result.status == "success"
        d = result.diagnostics[0]
        assert d.audio_start_ms == 0.0
        assert d.audio_end_ms == 500.0

    def test_empty_sentence_after_normalization(self) -> None:
        """Sentence that becomes empty after normalization is flagged."""
        tokens = self._make_tokens([("你好", 0, 300)])
        sentences = ["？。！"]

        svc = ForceAlignService()
        with patch.object(svc, "_transcribe", return_value=tokens):
            result = svc.align(None, sentences)

        assert result.status == "complete_mismatch"
        assert result.diagnostics[0].status == "no_match"

    def test_all_tokens_normalized_to_empty(self) -> None:
        """When whisper tokens are special markers like [MUSIC], they are filtered."""
        tokens = self._make_tokens([("[MUSIC]", 0, 1000)])
        sentences = ["你好。"]

        svc = ForceAlignService()
        with patch.object(svc, "_transcribe", return_value=tokens):
            result = svc.align(None, sentences)

        # [MUSIC] matches the whisper special pattern ^\[.*\]$ and is
        # filtered by _parse_whisper_json, so there are no usable tokens.
        assert result.status == "complete_mismatch"
        assert result.diagnostics[0].status == "no_match"


# ---------------------------------------------------------------------------
# ForceAlignResult model
# ---------------------------------------------------------------------------


class TestForceAlignResult:
    def test_success_result_field_defaults(self) -> None:
        r = ForceAlignResult(status="success")
        assert r.timings == []
        assert r.diagnostics == []
        assert r.message == ""

    def test_diagnostic_summary(self) -> None:
        d = ForceAlignDiagnostic(
            sentence_index=0,
            sentence_text="你好。",
            confidence=0.95,
            status="aligned",
            audio_start_ms=0.0,
            audio_end_ms=500.0,
        )
        summary = d.summary()
        assert "Sentence 0" in summary
        assert "你好。" in summary


# ---------------------------------------------------------------------------
# Confidence scoring precision
# ---------------------------------------------------------------------------


class TestConfidenceScoring:
    def test_perfect_match_gives_high_confidence(self) -> None:
        svc = ForceAlignService()
        tokens = [
            _Token("今天", 0, 500),
            _Token("天气", 500, 1000),
            _Token("真好", 1000, 1500),
        ]
        full_norm = "今天天气真好"
        char_to_token = [0, 0, 1, 1, 2, 2]

        confidence, _, _ = svc._match_sentence(
            "今天天气真好", full_norm, char_to_token, tokens
        )
        assert confidence == pytest.approx(1.0)

    def test_partial_match_gives_lower_confidence(self) -> None:
        svc = ForceAlignService()
        tokens = [
            _Token("今天", 0, 500),
            _Token("天气", 500, 1000),
            _Token("不好", 1000, 1500),
        ]
        full_norm = "今天天气不好"
        char_to_token = [0, 0, 1, 1, 2, 2]

        # "今天天气真好" vs "今天天气不好":
        #   "今天天气" (4 chars) and "好" (1 char) match = 5/6 ≈ 0.833
        confidence, _, _ = svc._match_sentence(
            "今天天气真好", full_norm, char_to_token, tokens
        )
        assert confidence == pytest.approx(5.0 / 6.0)

    def test_no_match_gives_zero_confidence(self) -> None:
        svc = ForceAlignService()
        tokens = [_Token("abc", 0, 300)]
        full_norm = "abc"
        char_to_token = [0, 0, 0]

        confidence, _, _ = svc._match_sentence(
            "你好世界", full_norm, char_to_token, tokens
        )
        assert confidence == 0.0
