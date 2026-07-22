"""Sentence-level TTS service.

Synthesizes each canonical Script Sentence separately, locks one resolved voice
for the whole Job, normalizes provider-specific edge silence, and persists
measured sentence timings.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from packages.pipeline_services.media_utils import (
    get_ffmpeg_path,
    get_media_duration,
    write_concat_file,
)
from packages.pipeline_services.script_sentence import (
    SentenceTiming,
    ScriptSentence,
    parse_script_sentences,
)
from packages.pipeline_services.tts_provider import (
    TTSConfigShim,
    TTSRetriesExhaustedError,
)


# Keys that affect the produced audio and therefore must be part of the cache
# fingerprint. Voice/model are the most important; style and tags also matter.
_FINGERPRINT_KEYS: tuple[str, ...] = (
    "model",
    "voice",
    "audio_format",
    "instructions",
    "language_type",
    "style_control_mode",
    "style_prompt",
    "director_character",
    "director_scene",
    "director_guidance",
    "audio_tags",
    "voice_clone_sample_path",
    "voice_design_prompt",
)


NormalizeFn = Callable[[Path, Path, str, int], None]
ConcatFn = Callable[[list[Path], Path], None]
DurationFn = Callable[[Path], float]


def _config_shim(config: dict[str, Any]) -> TTSConfigShim:
    """Build the duck-typed config object expected by the TTS providers."""
    return TTSConfigShim(config)


def _default_normalize_sentence_audio(
    input_path: Path,
    output_path: Path,
    audio_format: str,  # noqa: ARG001
    append_gap_ms: int,
    *,
    silence_db: int = -35,
) -> None:
    """Trim edge silence and append exactly ``append_gap_ms`` of silence.

    The output is a mono 16kHz WAV file so that all sentence clips can be
    concatenated without format mismatches.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = get_ffmpeg_path()
    gap_sec = append_gap_ms / 1000.0
    filter_expr = (
        f"silenceremove=start_periods=1:start_duration=0:start_threshold={silence_db}dB"
        f":stop_periods=-1:stop_duration=0:stop_threshold={silence_db}dB:detection=peak"
    )
    if gap_sec > 0:
        filter_expr += f",apad=pad_dur={gap_sec}"
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-af",
        filter_expr,
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_path),
    ]
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )


def _default_concat_audio_files(input_paths: list[Path], output_path: Path) -> None:
    """Concatenate WAV clips into a single MP3 file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = get_ffmpeg_path()
    concat_list = output_path.parent / f".{output_path.stem}_concat.txt"
    try:
        write_concat_file(concat_list, input_paths)
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(output_path),
        ]
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
    finally:
        if concat_list.exists():
            concat_list.unlink()


class SentenceTTSService:
    """Synthesize a script one canonical sentence at a time.

    Features:
      - shared Script Sentence parser
      - one resolved model/voice for the whole Job
      - per-sentence audio caching by text + model + voice + config fingerprint
      - per-sentence retry up to ``max_retries`` attempts
      - edge-silence normalization and exactly 200ms inter-sentence gap
      - measured sentence timings returned and persisted by the caller
    """

    def __init__(
        self,
        provider: Any,
        config: dict[str, Any],
        *,
        cache_dir: Path | str,
        max_retries: int = 3,
        silence_db: int = -35,
        gap_ms: int = 200,
        normalize_fn: NormalizeFn | None = None,
        concat_fn: ConcatFn | None = None,
        duration_fn: DurationFn | None = None,
    ) -> None:
        self.provider = provider
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.max_retries = max_retries
        self.silence_db = silence_db
        self.gap_ms = gap_ms
        self.normalize_fn = normalize_fn or _default_normalize_sentence_audio
        self.concat_fn = concat_fn or _default_concat_audio_files
        self.duration_fn = duration_fn or get_media_duration

    def synthesize_script(
        self, script_text: str, output_path: Path
    ) -> list[SentenceTiming]:
        """Synthesize *script_text* and write the combined audio to *output_path*.

        Sentences are synthesized with a fixed 4-worker thread pool.
        Results are back-filled by original sentence index so that
        ``concat_fn`` and ``_build_timings`` always receive the correct
        order regardless of which sentence finishes first.

        Returns the measured ``SentenceTiming`` list for each sentence.
        """
        sentences = parse_script_sentences(script_text)
        if not sentences:
            return []

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        locked_config = self._locked_config()
        script_sentences = [
            ScriptSentence(index=i, text=s) for i, s in enumerate(sentences)
        ]
        n = len(script_sentences)

        with tempfile.TemporaryDirectory(dir=Path(output_path).parent) as tmp:
            tmp_dir = Path(tmp)

            # Parallel synthesis with fixed 4-worker pool.
            # Each worker calls _synthesize_sentence which handles its own
            # per-sentence cache + retry.  Results are collected by future
            # and back-filled into raw_paths by original sentence index.
            raw_paths: list[Path] = [Path()] * n  # type: ignore[assignment]
            with ThreadPoolExecutor(max_workers=4) as executor:
                future_to_index = {}
                for i, sentence in enumerate(script_sentences):
                    future = executor.submit(
                        self._synthesize_sentence,
                        sentence.text,
                        locked_config,
                        tmp_dir,
                    )
                    future_to_index[future] = i

                for future in future_to_index:
                    i = future_to_index[future]
                    raw_paths[i] = future.result()

            # Normalize in original sentence order (concat + timings depend on it).
            normalized_paths: list[Path] = []
            for i in range(n):
                raw_path = raw_paths[i]
                is_last = i == n - 1
                norm_path = tmp_dir / f"{i:03d}_norm.wav"
                self.normalize_fn(
                    raw_path,
                    norm_path,
                    locked_config.get("audio_format", "wav"),
                    0 if is_last else self.gap_ms,
                )
                normalized_paths.append(norm_path)

            self.concat_fn(normalized_paths, output_path)
            return self._build_timings(normalized_paths, sentences, locked_config)

    def _locked_config(self) -> dict[str, Any]:
        """Return a config dict with voice randomization disabled so one voice is used."""
        cfg = dict(self.config)
        cfg["randomize_voice"] = False
        return cfg

    def _fingerprint(self, sentence: str, locked_config: dict[str, Any]) -> str:
        """Stable cache key for a sentence's audio."""
        hasher = hashlib.sha256()
        hasher.update(sentence.encode("utf-8"))
        cfg_slice = {k: locked_config.get(k) for k in _FINGERPRINT_KEYS}
        hasher.update(
            json.dumps(cfg_slice, sort_keys=True, ensure_ascii=False).encode("utf-8")
        )
        return hasher.hexdigest()

    def _synthesize_sentence(
        self, sentence: str, locked_config: dict[str, Any], tmp_dir: Path
    ) -> Path:
        """Return a path to the raw audio for *sentence*, using the cache when possible."""
        fp = self._fingerprint(sentence, locked_config)
        suffix = locked_config.get("audio_format", "wav") or "wav"
        cache_path = self.cache_dir / f"{fp}.{suffix}"

        if not cache_path.exists():
            audio_bytes = self._synthesize_with_retry(sentence, locked_config)
            cache_path.write_bytes(audio_bytes)

        return cache_path

    def _synthesize_with_retry(
        self, sentence: str, locked_config: dict[str, Any]
    ) -> bytes:
        """Call the provider for a single sentence, retrying up to ``max_retries``.

        Only transient / unknown errors are retried.  Permanent errors
        (``TTSBlockedError`` including ``TTSQuotaExceededError``) are raised
        immediately to avoid wasting time on unrecoverable failures (#249).
        When the retry budget is exhausted, a ``TTSRetriesExhaustedError`` is
        raised so the orchestrator does not add an additional phase-level
        retry (#266).
        """
        from packages.pipeline_services.tts_provider import TTSBlockedError

        shim = _config_shim(locked_config)
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self.provider.synthesize(sentence, shim)
            except TTSBlockedError:
                raise  # permanent failure — do not retry
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(
                    f"[TTS SENTENCE] Retry {attempt}/{self.max_retries} for {sentence!r}: {exc}",
                    flush=True,
                )
        assert last_error is not None
        raise TTSRetriesExhaustedError(last_error)

    def _build_timings(
        self,
        normalized_paths: list[Path],
        sentences: list[str],
        locked_config: dict[str, Any],
    ) -> list[SentenceTiming]:
        """Measure durations of the normalized sentence clips."""
        timings: list[SentenceTiming] = []
        start = 0.0
        model = locked_config.get("model", "")
        voice = locked_config.get("voice", "")
        for i, norm_path in enumerate(normalized_paths):
            duration = self.duration_fn(norm_path)
            timings.append(
                SentenceTiming(
                    index=i,
                    text=sentences[i],
                    start_seconds=start,
                    end_seconds=start + duration,
                    model=model,
                    voice=voice,
                )
            )
            start += duration
        return timings


__all__ = [
    "SentenceTTSService",
    "SentenceTiming",
    "ScriptSentence",
    "_config_shim",
]
