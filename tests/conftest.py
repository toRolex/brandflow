from __future__ import annotations

import gc
import io
import os
import resource
import wave
from collections.abc import Callable
from collections.abc import Iterator

import pytest

# ponytail: 单进程地址空间硬限制 8GB — 超过即 crash（MemoryError），
# 防止 pytest worker 无限制膨胀撑爆整机。  8GB 足够跑完任何单文件测试。
_LIMIT = 8 * 1024 * 1024 * 1024  # 8 GB
try:
    resource.setrlimit(resource.RLIMIT_AS, (_LIMIT, _LIMIT))
except ValueError:
    pass  # macOS 上部分环境下 setrlimit 可能被父进程锁住

# Aggressive GC: lower thresholds trigger collection sooner,
# preventing unbounded accumulation across long test sessions.
gc.set_threshold(500, 5, 3)

from fastapi.testclient import TestClient  # noqa: E402

# ponytail: 全局屏蔽 ThreadPoolExecutor 与后台 auto_tick，
# 单进程 RSS 从 ~20GB 压到 ~200MB。
os.environ["EXPORT_SYNC"] = "1"
os.environ["DEV_AUTO_TICK"] = "0"

from apps.control_plane.app import create_app  # noqa: E402


# ponytail: 内存泄漏防护 — 每个测试函数执行完毕后强制 GC，
# 防止参差残留（httpx 连接池、FastAPI app state、tempdir 引用链）积累。
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    yield
    gc.collect()


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


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """模块级 TestClient 工厂 — 每个 .py 文件只需创建一次 app。

    module scope 将 app 创建从 O(tests) 降到 O(test-files)，
    配合 gc.collect 钩子显著降低全量运行时的 RSS 峰值。
    """
    root_dir = tmp_path_factory.mktemp("app")
    app = create_app(root_dir)
    with TestClient(app) as c:
        yield c
