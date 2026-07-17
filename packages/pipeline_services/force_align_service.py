"""Force alignment service for uploaded audio.

Runs whisper-cli on an uploaded audio file, extracts word-level timestamps,
and aligns them against canonical Script Sentences to produce per-sentence
SentenceTiming objects.  Fails with structured diagnostics when alignment
confidence is insufficient.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, Field

from packages.pipeline_services.media_utils import (
    get_whisper_cli_path,
    get_whisper_model_path,
)
from packages.pipeline_services.script_sentence import SentenceTiming

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ForceAlignDiagnostic(BaseModel):
    """Per-sentence diagnostic from a force alignment attempt."""

    model_config = ConfigDict(extra="forbid")

    sentence_index: int = Field(ge=0)
    sentence_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["aligned", "low_confidence", "no_match"]
    audio_start_ms: float | None = None
    audio_end_ms: float | None = None

    def summary(self) -> str:
        """One-line human-readable summary of this diagnostic."""
        match self.status:
            case "aligned":
                return (
                    f"Sentence {self.sentence_index} "
                    f"({self.sentence_text}) aligned at "
                    f"{self.audio_start_ms:.0f}-{self.audio_end_ms:.0f} ms "
                    f"(conf={self.confidence:.2f})"
                )
            case "low_confidence":
                return (
                    f"Sentence {self.sentence_index} "
                    f"({self.sentence_text}) low confidence "
                    f"(conf={self.confidence:.2f}"
                    f"{f', audio={self.audio_start_ms:.0f}-{self.audio_end_ms:.0f} ms' if self.audio_start_ms is not None else ''})"
                )
            case _:
                return (
                    f"Sentence {self.sentence_index} "
                    f"({self.sentence_text}) no match found in audio"
                )


class ForceAlignResult(BaseModel):
    """Outcome of a force alignment run.

    ``timings`` contains ``SentenceTiming`` entries only for sentences that
    met the confidence threshold; ``diagnostics`` covers every sentence so
    callers know which ones passed and which did not.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "partial_mismatch", "complete_mismatch"]
    timings: list[SentenceTiming] = Field(default_factory=list)
    diagnostics: list[ForceAlignDiagnostic] = Field(default_factory=list)
    message: str = ""


class ForceAlignError(Exception):
    """Raised when forced alignment fails or partially fails.

    Carries the full ``ForceAlignResult`` so callers can render per-sentence
    diagnostics (audio ranges, confidence scores) to the user.
    """

    def __init__(self, result: ForceAlignResult) -> None:
        self.result = result
        detail = "\n".join(d.summary() for d in result.diagnostics)
        super().__init__(f"{result.message}\n{detail}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _Token(NamedTuple):
    """A single whisper token with text and millisecond offsets."""

    text: str
    start_ms: float
    end_ms: float


_PUNCTUATION_RE = re.compile(r"[^\w一-鿿㐀-䶿]", re.UNICODE)
_WHISPER_SPECIAL_RE = re.compile(r"^\[.*\]$")


def _normalize(text: str) -> str:
    """Strip punctuation and whitespace for text matching.

    Preserves CJK characters (U+4E00-U+9FFF) and Latin word characters.
    """
    return _PUNCTUATION_RE.sub("", text).lower().strip()


def _is_whisper_special(text: str) -> bool:
    """Return True when *text* is a whisper special marker like [_BEG_]."""
    return bool(_WHISPER_SPECIAL_RE.match(text.strip()))


def _parse_whisper_json(json_text: str) -> list[_Token]:
    """Extract non-special tokens with millisecond offsets from whisper JSON.

    Returns an empty list when the transcription contains no usable segments.
    """
    try:
        data = json.loads(json_text)
    except (json.JSONDecodeError, TypeError):
        return []

    transcription: list[dict[str, Any]] = data.get("transcription", [])
    if not isinstance(transcription, list):
        return []

    tokens: list[_Token] = []
    for segment in transcription:
        if not isinstance(segment, dict):
            continue
        segment_tokens: list[dict[str, Any]] = segment.get("tokens", [])
        for token in segment_tokens:
            if not isinstance(token, dict):
                continue
            text = (token.get("text") or "").strip()
            if not text or _is_whisper_special(text):
                continue

            offsets: dict[str, Any] | None = token.get("offsets")
            if isinstance(offsets, dict):
                start_ms = float(offsets.get("from", 0))
                end_ms = float(offsets.get("to", 0))
            else:
                timestamps: dict[str, Any] | None = token.get("timestamps")
                if isinstance(timestamps, dict):
                    start_ms = _ts_to_ms(timestamps.get("from", "00:00:00,000"))
                    end_ms = _ts_to_ms(timestamps.get("to", "00:00:00,000"))
                else:
                    continue

            tokens.append(_Token(text=text, start_ms=start_ms, end_ms=end_ms))

    return tokens


def _ts_to_ms(timestamp: str) -> float:
    """Convert HH:MM:SS,mmm to milliseconds."""
    parts = timestamp.replace(",", ":").split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2])
    ms = int(parts[3]) if len(parts) > 3 else 0
    return h * 3600000 + m * 60000 + s * 1000 + ms


# ---------------------------------------------------------------------------
# ForceAlignService
# ---------------------------------------------------------------------------


class ForceAlignService:
    """Force-align uploaded audio to canonical Script Sentences.

    Uses whisper-cli for ASR with word-level timestamps, then matches
    recognized words to known sentences via text similarity.

    Parameters
    ----------
    confidence_threshold : float
        Minimum ``SequenceMatcher.ratio()`` for a sentence to be considered
        aligned (default 0.6).
    whisper_timeout : int
        Subprocess timeout in seconds for whisper-cli (default 600).
    """

    def __init__(
        self,
        *,
        confidence_threshold: float = 0.6,
        whisper_timeout: int = 600,
    ) -> None:
        if not 0.0 < confidence_threshold <= 1.0:
            raise ValueError(
                f"confidence_threshold must be in (0.0, 1.0], got {confidence_threshold}"
            )
        self.confidence_threshold = confidence_threshold
        self.whisper_timeout = whisper_timeout

    # -- public API ---------------------------------------------------------

    def align(self, audio_path: Path, sentences: list[str]) -> ForceAlignResult:
        """Force-align *audio_path* to *sentences*.

        Returns a ``ForceAlignResult`` whose ``status`` is one of
        ``success`` (all sentences met threshold), ``partial_mismatch``
        (some matched, some did not), or ``complete_mismatch`` (no
        sentence met threshold).
        """
        if not sentences:
            return ForceAlignResult(
                status="complete_mismatch",
                message="No sentences provided for alignment.",
            )

        tokens = self._transcribe(audio_path)
        if not tokens:
            return ForceAlignResult(
                status="complete_mismatch",
                diagnostics=[
                    ForceAlignDiagnostic(
                        sentence_index=i,
                        sentence_text=s,
                        confidence=0.0,
                        status="no_match",
                    )
                    for i, s in enumerate(sentences)
                ],
                message="No speech tokens detected in audio.",
            )

        # Build normalized full text and character-to-token index
        norm_parts: list[str] = []
        char_to_token: list[int] = []
        for tidx, token in enumerate(tokens):
            normed = _normalize(token.text)
            for _ in normed:
                char_to_token.append(tidx)
            norm_parts.append(normed)
        full_norm = "".join(norm_parts)

        if not full_norm:
            return ForceAlignResult(
                status="complete_mismatch",
                diagnostics=[
                    ForceAlignDiagnostic(
                        sentence_index=i,
                        sentence_text=s,
                        confidence=0.0,
                        status="no_match",
                    )
                    for i, s in enumerate(sentences)
                ],
                message="No normalisable text found in transcription.",
            )

        # Align each sentence
        diagnostics: list[ForceAlignDiagnostic] = []
        timings: list[SentenceTiming] = []
        aligned_count = 0

        for i, sentence in enumerate(sentences):
            sent_norm = _normalize(sentence)
            if not sent_norm:
                diagnostics.append(
                    ForceAlignDiagnostic(
                        sentence_index=i,
                        sentence_text=sentence,
                        confidence=0.0,
                        status="no_match",
                    )
                )
                continue

            confidence, start_tok, end_tok = self._match_sentence(
                sent_norm, full_norm, char_to_token, tokens
            )

            if confidence >= self.confidence_threshold:
                start_ms = tokens[start_tok].start_ms
                end_ms = tokens[end_tok].end_ms
                timings.append(
                    SentenceTiming(
                        index=i,
                        text=sentence,
                        start_seconds=start_ms / 1000.0,
                        end_seconds=end_ms / 1000.0,
                        model="whisper",
                        voice="upload",
                    )
                )
                diagnostics.append(
                    ForceAlignDiagnostic(
                        sentence_index=i,
                        sentence_text=sentence,
                        confidence=confidence,
                        status="aligned",
                        audio_start_ms=start_ms,
                        audio_end_ms=end_ms,
                    )
                )
                aligned_count += 1
            elif confidence > 0.0:
                # Low confidence — we have a best-guess span
                start_ms = tokens[start_tok].start_ms
                end_ms = tokens[end_tok].end_ms
                diagnostics.append(
                    ForceAlignDiagnostic(
                        sentence_index=i,
                        sentence_text=sentence,
                        confidence=confidence,
                        status="low_confidence",
                        audio_start_ms=start_ms,
                        audio_end_ms=end_ms,
                    )
                )
            else:
                diagnostics.append(
                    ForceAlignDiagnostic(
                        sentence_index=i,
                        sentence_text=sentence,
                        confidence=0.0,
                        status="no_match",
                    )
                )

        total = len(sentences)
        if aligned_count == total:
            return ForceAlignResult(
                status="success",
                timings=timings,
                diagnostics=diagnostics,
                message=f"All {total} sentences aligned successfully.",
            )
        if aligned_count > 0:
            return ForceAlignResult(
                status="partial_mismatch",
                timings=timings,
                diagnostics=diagnostics,
                message=(
                    f"{aligned_count}/{total} sentences aligned; "
                    f"{total - aligned_count} sentences did not meet "
                    f"the confidence threshold ({self.confidence_threshold})."
                ),
            )
        return ForceAlignResult(
            status="complete_mismatch",
            diagnostics=diagnostics,
            message=(
                f"No sentence met the confidence threshold "
                f"({self.confidence_threshold}); {total} sentences evaluated."
            ),
        )

    # -- internal helpers ---------------------------------------------------

    def _transcribe(self, audio_path: Path) -> list[_Token]:
        """Run whisper-cli and return token-level timestamps.

        Overridable in tests (mock the subprocess call).
        """
        if not audio_path.exists():
            return []

        whisper_cli = get_whisper_cli_path()
        model_path = get_whisper_model_path()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            output_prefix = tmp / "whisper_out"

            cmd = [
                whisper_cli,
                "-m",
                model_path,
                "-f",
                str(audio_path),
                "-l",
                "zh",
                "-oj",
                "-of",
                str(output_prefix),
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.whisper_timeout,
            )

            json_path = tmp / "whisper_out.json"
            if not json_path.exists():
                # Try parsing stdout as fallback (some builds print JSON
                # directly when -oj is given without -of).
                if proc.stdout.strip():
                    return _parse_whisper_json(proc.stdout)
                return []

            raw = json_path.read_text(encoding="utf-8")
            return _parse_whisper_json(raw)

    @staticmethod
    def _match_sentence(
        sent_norm: str,
        full_norm: str,
        char_to_token: list[int],
        tokens: list[_Token],
    ) -> tuple[float, int, int]:
        """Return ``(confidence, start_token_idx, end_token_idx)``.

        Uses ``difflib.SequenceMatcher.get_matching_blocks()`` to find the
        best character-level alignment and derive token-level timing bounds.
        """
        if not sent_norm or not full_norm:
            return 0.0, 0, 0

        sm = SequenceMatcher(None, sent_norm, full_norm)
        blocks = sm.get_matching_blocks()
        # blocks[-1] is the sentinel (len_a, len_b, 0)
        matched = [(a, b, n) for a, b, n in blocks if n > 0]

        if not matched:
            return 0.0, 0, 0

        total_matched = sum(n for _, _, n in matched)
        confidence = total_matched / len(sent_norm)

        # Map character positions to token indices
        span_start = matched[0][1]
        span_end = matched[-1][1] + matched[-1][2]

        max_idx = len(char_to_token) - 1
        start_tok = char_to_token[min(span_start, max_idx)]
        end_tok = char_to_token[min(max(0, span_end - 1), max_idx)]

        # Clamp: ensure end_tok is within range
        if end_tok >= len(tokens):
            end_tok = len(tokens) - 1
        if start_tok > end_tok:
            start_tok = end_tok

        return confidence, start_tok, end_tok


__all__ = [
    "ForceAlignDiagnostic",
    "ForceAlignError",
    "ForceAlignResult",
    "ForceAlignService",
]
