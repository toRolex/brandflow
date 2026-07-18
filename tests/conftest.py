from __future__ import annotations

import io
import wave
from collections.abc import Callable

import pytest


@pytest.fixture
def wav_bytes() -> Callable[[int], bytes]:
    def build(frame_count: int = 240) -> bytes:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(b"\x00\x00" * frame_count)
        return output.getvalue()

    return build
