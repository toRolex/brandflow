"""Tests for SentenceTTSService — per-sentence TTS with cache, retry, and timing.

The tests inject fake audio helpers so that FFmpeg is not required for the
unit-level logic; a separate conditional test covers the real FFmpeg helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from packages.pipeline_services.sentence_tts_service import (
    SentenceTTSService,
    SentenceTiming,
    _config_shim,
)


class _RecordingHelpers:
    """Recordable fake audio helpers for unit testing."""

    def __init__(self) -> None:
        self.normalize_calls: list[tuple[Path, Path, str, int]] = []
        self.concat_calls: list[list[Path]] = []

    def make_normalize(self):
        def _normalize(
            input_path: Path, output_path: Path, audio_format: str, append_gap_ms: int
        ) -> None:
            self.normalize_calls.append(
                (input_path, output_path, audio_format, append_gap_ms)
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(input_path.read_bytes())

        return _normalize

    def make_concat(self):
        def _concat(input_paths: list[Path], output_path: Path) -> None:
            self.concat_calls.append(input_paths)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"".join(p.read_bytes() for p in input_paths))

        return _concat


@pytest.fixture()
def base_config() -> dict[str, Any]:
    return {
        "model": "mimo-v2.5-tts",
        "voice": "Mia",
        "audio_format": "wav",
        "instructions": "",
        "language_type": "Chinese",
        "optimize_instructions": False,
        "fallback_voice": "Dean",
        "randomize_voice": True,
        "random_voices": ["Mia", "Dean"],
        "style_control_mode": "simple",
        "style_prompt": "自然 清晰",
        "voice_design_prompt": "",
        "audio_tags_enabled": False,
        "audio_tags": "",
        "voice_clone_sample_path": "",
        "voice_clone_mime_type": "",
        "optimize_text_preview": False,
        "director_character": "",
        "director_scene": "",
        "director_guidance": "",
    }


class TestSentenceTTSService:
    def _make_service(
        self,
        provider,
        config: dict[str, Any],
        cache_dir: Path,
        helpers: _RecordingHelpers,
        max_retries: int = 3,
    ) -> SentenceTTSService:
        return SentenceTTSService(
            provider=provider,
            config=config,
            cache_dir=cache_dir,
            max_retries=max_retries,
            gap_ms=200,
            normalize_fn=helpers.make_normalize(),
            concat_fn=helpers.make_concat(),
            duration_fn=lambda _path: 1.5,
        )

    def test_resolves_single_model_and_voice_for_all_sentences(
        self, base_config, tmp_path
    ) -> None:
        provider = MagicMock()
        provider.synthesize.return_value = b"audio"
        helpers = _RecordingHelpers()
        service = self._make_service(provider, base_config, tmp_path, helpers)

        service.synthesize_script("第一句。第二句。", tmp_path / "out.mp3")

        assert provider.synthesize.call_count == 2
        for call in provider.synthesize.call_args_list:
            config_obj = call.args[1]
            assert config_obj.model == "mimo-v2.5-tts"
            assert config_obj.voice == "Mia"
            assert config_obj.randomize_voice is False

    def test_synthesizes_each_sentence_once(self, base_config, tmp_path) -> None:
        provider = MagicMock()
        provider.synthesize.return_value = b"audio"
        helpers = _RecordingHelpers()
        service = self._make_service(provider, base_config, tmp_path, helpers)

        service.synthesize_script("第一句。第二句！", tmp_path / "out.mp3")

        assert provider.synthesize.call_count == 2
        assert provider.synthesize.call_args_list[0].args[0] == "第一句。"
        assert provider.synthesize.call_args_list[1].args[0] == "第二句！"

    def test_caches_by_sentence_fingerprint(self, base_config, tmp_path) -> None:
        provider = MagicMock()
        provider.synthesize.return_value = b"audio"
        helpers = _RecordingHelpers()
        service = self._make_service(provider, base_config, tmp_path, helpers)

        out1 = tmp_path / "out1.mp3"
        out2 = tmp_path / "out2.mp3"
        service.synthesize_script("同一句。", out1)
        service.synthesize_script("同一句。", out2)

        # One provider call even though the script was synthesized twice.
        assert provider.synthesize.call_count == 1

    def test_retries_failed_sentence_up_to_three_times(
        self, base_config, tmp_path
    ) -> None:
        provider = MagicMock()
        provider.synthesize.side_effect = [
            RuntimeError("TTS down"),
            RuntimeError("TTS down again"),
            b"audio",
        ]
        helpers = _RecordingHelpers()
        service = self._make_service(
            provider, base_config, tmp_path, helpers, max_retries=3
        )

        timings = service.synthesize_script("第一句。", tmp_path / "out.mp3")

        assert provider.synthesize.call_count == 3
        assert len(timings) == 1

    def test_fails_after_exhausting_retries(self, base_config, tmp_path) -> None:
        provider = MagicMock()
        provider.synthesize.side_effect = [
            RuntimeError("TTS down"),
            RuntimeError("TTS down"),
            RuntimeError("TTS down"),
        ]
        helpers = _RecordingHelpers()
        service = self._make_service(
            provider, base_config, tmp_path, helpers, max_retries=3
        )

        with pytest.raises(RuntimeError, match="TTS down"):
            service.synthesize_script("第一句。", tmp_path / "out.mp3")

        assert provider.synthesize.call_count == 3

    def test_successful_sentences_not_regenerated(self, base_config, tmp_path) -> None:
        provider = MagicMock()
        # Sentence 1 fails once, then succeeds; sentence 2 succeeds first time.
        provider.synthesize.side_effect = [
            RuntimeError("TTS down"),
            b"audio1",
            b"audio2",
        ]
        helpers = _RecordingHelpers()
        service = self._make_service(
            provider, base_config, tmp_path, helpers, max_retries=3
        )

        service.synthesize_script("第一句。第二句。", tmp_path / "run1.mp3")
        # Second run should be fully cache-driven.
        service.synthesize_script("第一句。第二句。", tmp_path / "run2.mp3")

        assert provider.synthesize.call_count == 3

    def test_normalizes_edge_silence_with_200ms_gap(
        self, base_config, tmp_path
    ) -> None:
        provider = MagicMock()
        provider.synthesize.return_value = b"audio"
        helpers = _RecordingHelpers()
        service = self._make_service(provider, base_config, tmp_path, helpers)

        service.synthesize_script("第一句。第二句。第三句。", tmp_path / "out.mp3")

        # All sentences except the last get a 200ms gap appended to the previous segment.
        gaps = [call[3] for call in helpers.normalize_calls]
        assert gaps == [200, 200, 0]

    def test_persists_sentence_timings(self, base_config, tmp_path) -> None:
        provider = MagicMock()
        provider.synthesize.return_value = b"audio"
        helpers = _RecordingHelpers()
        service = self._make_service(provider, base_config, tmp_path, helpers)

        timings = service.synthesize_script("第一句。第二句。", tmp_path / "out.mp3")

        assert len(timings) == 2
        assert all(isinstance(t, SentenceTiming) for t in timings)
        assert timings[0].index == 0
        assert timings[0].text == "第一句。"
        assert timings[0].start_seconds == 0.0
        assert timings[0].end_seconds == 1.5
        assert timings[1].index == 1
        assert timings[1].text == "第二句。"
        assert timings[1].start_seconds == 1.5
        assert timings[1].end_seconds == 3.0

    def test_duration_fn_used_for_measured_timing(self, base_config, tmp_path) -> None:
        provider = MagicMock()
        provider.synthesize.return_value = b"audio"
        helpers = _RecordingHelpers()
        service = SentenceTTSService(
            provider=provider,
            config=base_config,
            cache_dir=tmp_path,
            normalize_fn=helpers.make_normalize(),
            concat_fn=helpers.make_concat(),
            duration_fn=lambda _path: 2.25,
        )

        timings = service.synthesize_script("第一句。", tmp_path / "out.mp3")

        assert timings[0].end_seconds == 2.25


class TestConfigShim:
    def test_config_shim_supplies_defaults(self, base_config) -> None:
        shim = _config_shim({})
        assert shim.model == "mimo-v2.5-tts"
        assert shim.voice == "Mia"

    def test_config_shim_respects_provided_values(self, base_config) -> None:
        shim = _config_shim(base_config)
        assert shim.model == "mimo-v2.5-tts"
        assert shim.voice == "Mia"


# ---------------------------------------------------------------------------
# Parallel TTS (Issue #266)
# ---------------------------------------------------------------------------


class TestParallelTTS:
    """Thread-pool parallel synthesis with index-ordered results."""

    def _make_service(
        self,
        provider: Any,
        config: dict[str, Any],
        cache_dir: Path,
        helpers: _RecordingHelpers,
    ) -> SentenceTTSService:
        return SentenceTTSService(
            provider=provider,
            config=config,
            cache_dir=cache_dir,
            gap_ms=200,
            normalize_fn=helpers.make_normalize(),
            concat_fn=helpers.make_concat(),
            duration_fn=lambda _path: 1.5,
        )

    def test_parallel_synthesis_produces_ordered_timings(
        self, base_config, tmp_path
    ) -> None:
        """Output SentenceTiming list must be in original sentence index order,
        regardless of provider completion order."""
        provider = MagicMock()
        provider.synthesize.return_value = b"audio"
        helpers = _RecordingHelpers()
        service = self._make_service(provider, base_config, tmp_path, helpers)

        # 6 sentences — enough to exercise the 4-worker pool (at least 2 batches)
        timings = service.synthesize_script(
            "第一句。第二句。第三句。第四句。第五句。第六句。",
            tmp_path / "out.mp3",
        )

        assert len(timings) == 6
        # Every timing must have its index matching its position.
        for pos, t in enumerate(timings):
            assert t.index == pos, (
                f"timings[{pos}].index == {t.index}, expected {pos}"
            )
        # Also verify the text matches.
        expected = ["第一句。", "第二句。", "第三句。", "第四句。", "第五句。", "第六句。"]
        for i, exp in enumerate(expected):
            assert timings[i].text == exp, (
                f"timings[{i}].text == {timings[i].text!r}, expected {exp!r}"
            )

    def test_parallel_synthesis_calls_provider_concurrently(
        self, base_config, tmp_path
    ) -> None:
        """Use a fake provider that records thread IDs to prove concurrent execution."""
        import threading

        thread_ids: list[int] = []
        lock = threading.Lock()

        class _ThreadTrackingProvider:
            def synthesize(self, text: str, config: Any) -> bytes:
                with lock:
                    thread_ids.append(threading.get_ident())
                # Small sleep to increase chance of interleaving
                import time

                time.sleep(0.01)
                return b"audio"

        provider = _ThreadTrackingProvider()
        helpers = _RecordingHelpers()
        service = self._make_service(provider, base_config, tmp_path, helpers)

        service.synthesize_script(
            "第一句。第二句。第三句。第四句。第五句。第六句。",
            tmp_path / "out.mp3",
        )

        # At least 2 distinct threads means concurrency was used.
        distinct_threads = set(thread_ids)
        assert len(distinct_threads) >= 2, (
            f"Expected >= 2 distinct threads, got {distinct_threads}"
        )

    def test_parallel_synthesis_respects_cache(
        self, base_config, tmp_path
    ) -> None:
        """Pre-populated cache entries skip provider calls during parallel synthesis."""
        provider = MagicMock()
        provider.synthesize.return_value = b"audio"
        helpers = _RecordingHelpers()
        service = self._make_service(provider, base_config, tmp_path, helpers)

        # Pre-populate cache for the first three sentences.
        locked_config = service._locked_config()
        for text in ["第一句。", "第二句。", "第三句。"]:
            fp = service._fingerprint(text, locked_config)
            suffix = locked_config.get("audio_format", "wav") or "wav"
            cache_path = service.cache_dir / f"{fp}.{suffix}"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(b"cached_audio")

        # Now synthesize — first three should hit cache.
        provider.synthesize.reset_mock()
        service.synthesize_script(
            "第一句。第二句。第三句。第四句。第五句。第六句。",
            tmp_path / "out.mp3",
        )

        # Provider should only be called for uncached sentences (后三句).
        # Call count = 3 (only 第四/五/六 need synthesis).
        assert provider.synthesize.call_count == 3, (
            f"Expected 3 provider calls, got {provider.synthesize.call_count}"
        )
        # Verify cached sentences were NOT synthesized.
        synthesized_texts = [
            call.args[0] for call in provider.synthesize.call_args_list
        ]
        for cached_text in ["第一句。", "第二句。", "第三句。"]:
            assert cached_text not in synthesized_texts, (
                f"Cached sentence {cached_text!r} should not be synthesized"
            )
