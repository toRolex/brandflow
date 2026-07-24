from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from packages.log_service.excepthook import install_global_excepthook


@pytest.fixture(autouse=True)
def _reset_excepthook_state() -> Iterator[None]:
    import packages.log_service.excepthook as excepthook_module

    original = sys.excepthook
    excepthook_module._original_excepthook = None
    yield
    sys.excepthook = original
    excepthook_module._original_excepthook = None


@pytest.fixture
def _log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(
        "packages.log_service.log_writer.get_log_dir",
        lambda: log_dir,
    )
    yield log_dir


def _latest_log_file(log_dir: Path) -> Path:
    return log_dir / f"{datetime.now(tz=UTC).astimezone().date().isoformat()}.jsonl"


def test_install_global_excepthook_preserves_original_chain(_log_dir: Path) -> None:
    original_calls: list[tuple] = []

    def fake_original(
        exc_type: type[BaseException],
        exc_value: BaseException | None,
        exc_tb: object,
    ) -> None:
        original_calls.append((exc_type, exc_value, exc_tb))

    sys.excepthook = fake_original
    install_global_excepthook()

    assert sys.excepthook is not fake_original

    exc = ValueError("direct test")
    sys.excepthook(type(exc), exc, exc.__traceback__)

    assert len(original_calls) == 1
    assert original_calls[0][0] is type(exc)
    assert original_calls[0][1] is exc

    log_file = _latest_log_file(_log_dir)
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source"] == "backend"
    assert parsed["level"] == "error"
    assert parsed["message"] == "direct test"
    assert "ValueError" in parsed["stack_trace"]


def test_excepthook_logs_uncaught_thread_exception(
    _log_dir: Path,
    capsys: pytest.CaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_global_excepthook()

    def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
        sys.excepthook(args.exc_type, args.exc_value, args.exc_traceback)

    monkeypatch.setattr(threading, "excepthook", _thread_excepthook)

    def raise_exception() -> None:
        raise RuntimeError("thread boom")

    thread = threading.Thread(target=raise_exception)
    thread.start()
    thread.join()

    log_file = _latest_log_file(_log_dir)
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source"] == "backend"
    assert parsed["level"] == "error"
    assert parsed["message"] == "thread boom"
    assert "RuntimeError" in parsed["stack_trace"]

    captured = capsys.readouterr()
    assert "thread boom" in captured.err
