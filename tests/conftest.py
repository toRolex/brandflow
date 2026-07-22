from __future__ import annotations

import io
import os
import wave
from collections.abc import Callable
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ponytail: 全局屏蔽 ThreadPoolExecutor 与后台 auto_tick，
# 单进程 RSS 从 ~20GB 压到 ~200MB。
os.environ.setdefault("EXPORT_SYNC", "1")
os.environ.setdefault("DEV_AUTO_TICK", "0")

from apps.control_plane.app import create_app  # noqa: E402


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


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """统一 TestClient 工厂，teardown 释放 httpx 连接池与 lifespan。"""
    app = create_app(tmp_path)
    with TestClient(app) as c:
        yield c
