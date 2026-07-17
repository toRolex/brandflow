"""Shared Script Sentence parser and models.

A Script Sentence is the canonical unit of the spoken script. It is ended by
sentence-ending punctuation (``。！？!?``) or a line break. Clause punctuation
(``,，、；;:：``) does not split a sentence, empty lines are ignored, and the
ending punctuation is preserved as part of the sentence text.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict


_SENTENCE_END_RE = re.compile(r"[。！？!?]")


class ScriptSentence(BaseModel):
    """One canonical sentence from the script."""

    model_config = ConfigDict(extra="forbid")

    index: int
    text: str


class SentenceTiming(BaseModel):
    """Measured audio timing for a single Script Sentence."""

    model_config = ConfigDict(extra="forbid")

    index: int
    text: str
    start_seconds: float
    end_seconds: float
    model: str = ""
    voice: str = ""


def parse_script_sentences(text: str | None) -> list[str]:
    """Split *text* into canonical Script Sentences.

    Rules:
      - ``。！？!?`` end a sentence.
      - Line breaks end a sentence.
      - Clause punctuation (e.g. ``,，、；;:：``) does not split sentences.
      - Empty/whitespace-only lines are ignored.
      - Sentence-ending punctuation remains attached to the sentence text.
    """
    if not text:
        return []

    sentences: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        cursor = 0
        buffer = ""
        for match in _SENTENCE_END_RE.finditer(line):
            buffer += line[cursor : match.end()]
            stripped = buffer.strip()
            if stripped:
                sentences.append(stripped)
            buffer = ""
            cursor = match.end()

        # Remaining text after the last sentence-ending punctuation is ended by
        # the line break unless the line was already fully consumed.
        remainder = line[cursor:].strip()
        if remainder:
            buffer += remainder
            stripped = buffer.strip()
            if stripped:
                sentences.append(stripped)
            buffer = ""

    return sentences
