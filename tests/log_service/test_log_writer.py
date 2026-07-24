from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from packages.log_service.log_writer import get_log_dir, log_error


class _FakePlatformDirs:
    def __init__(self, base: Path) -> None:
        self.base = base

    def __call__(self, app: str, appauthor: bool | None = None) -> str:
        return str(self.base)


def _make_log_dir(tmp_path: Path) -> Path:
    """Return a per-test log directory that overrides get_log_dir()."""
    return tmp_path / "logs"


def test_log_error_writes_jsonl(tmp_path: Path) -> None:
    log_dir = _make_log_dir(tmp_path)
    entry = {"source": "backend", "level": "error", "message": "test message"}

    log_file = log_error(entry, log_dir=log_dir)

    assert log_file == log_dir / f"{datetime.now(tz=UTC).astimezone().date().isoformat()}.jsonl"
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source"] == "backend"
    assert parsed["level"] == "error"
    assert parsed["message"] == "test message"
    assert "timestamp" in parsed


def test_log_error_appends_to_same_file(tmp_path: Path) -> None:
    log_dir = _make_log_dir(tmp_path)

    log_error({"source": "backend", "level": "error", "message": "first"}, log_dir=log_dir)
    log_error({"source": "frontend", "level": "warn", "message": "second"}, log_dir=log_dir)

    log_file = log_dir / f"{datetime.now(tz=UTC).astimezone().date().isoformat()}.jsonl"
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["message"] == "first"
    assert json.loads(lines[1])["message"] == "second"


def test_log_error_creates_directory(tmp_path: Path) -> None:
    log_dir = tmp_path / "brandflow" / "logs"
    assert not log_dir.exists()

    log_error({"source": "backend", "level": "error", "message": "test"}, log_dir=log_dir)

    assert log_dir.exists()
    assert log_dir.is_dir()


def test_log_error_preserves_existing_timestamp(tmp_path: Path) -> None:
    log_dir = _make_log_dir(tmp_path)
    entry = {
        "source": "backend",
        "level": "error",
        "message": "test",
        "timestamp": "2026-07-24T10:00:00+08:00",
    }

    log_error(entry, log_dir=log_dir)

    log_file = log_dir / f"{datetime.now(tz=UTC).astimezone().date().isoformat()}.jsonl"
    parsed = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert parsed["timestamp"] == "2026-07-24T10:00:00+08:00"


def test_log_error_non_serialisable_values(tmp_path: Path) -> None:
    log_dir = _make_log_dir(tmp_path)

    class Dummy:
        def __str__(self) -> str:
            return "dummy-value"

    log_error(
        {"source": "backend", "level": "error", "message": "test", "extra": {"obj": Dummy()}},
        log_dir=log_dir,
    )

    log_file = log_dir / f"{datetime.now(tz=UTC).astimezone().date().isoformat()}.jsonl"
    parsed = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert parsed["extra"]["obj"] == "dummy-value"


def test_log_error_thread_safety(tmp_path: Path) -> None:
    log_dir = _make_log_dir(tmp_path)
    errors: list[dict] = [
        {"source": "backend", "level": "error", "message": f"msg-{i}"}
        for i in range(100)
    ]

    def write(entry: dict) -> None:
        log_error(entry, log_dir=log_dir)

    threads = [threading.Thread(target=write, args=(e,)) for e in errors]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    log_file = log_dir / f"{datetime.now(tz=UTC).astimezone().date().isoformat()}.jsonl"
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 100
    parsed = [json.loads(line) for line in lines]
    assert {p["message"] for p in parsed} == {f"msg-{i}" for i in range(100)}


def test_get_log_dir_returns_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = tmp_path / "brandflow-data"
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        _FakePlatformDirs(base),
    )

    result = get_log_dir()

    assert result == base / "logs"
