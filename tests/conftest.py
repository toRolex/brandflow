from __future__ import annotations

import gc
import io
import os
import resource
import wave
from collections.abc import Callable
from collections.abc import Iterator

import pytest

# ponytail: 单进程地址空间硬限制 3GB — 超过即 crash（MemoryError）。
# 正常单文件测试峰值 < 500MB（含 pipeline services < 1.5GB），
# 3GB 远高于正常峰值但能卡住泄漏（2GB+/进程持续增长）。
# 配合 -n 2 worker：2×3GB + 系统开销 ≈ 8GB，24GB 机器安全。
#
# 注意：macOS 上进程 VSZ 因系统框架映射已 ~400GB，setrlimit 设 3GB 会被内核拒绝。
# 此保护在 Linux CI 环境中生效（VSZ ≈ RSS），macOS 本地不生效，保留作 CI 兼容。
_LIMIT = 3 * 1024 * 1024 * 1024  # 3 GB
try:
    resource.setrlimit(resource.RLIMIT_AS, (_LIMIT, _LIMIT))
except ValueError:
    pass

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
    gc.collect()
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
