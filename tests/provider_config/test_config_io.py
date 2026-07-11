"""Tests for packages.provider_config.config_io."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

import pytest

from packages.provider_config.config_io import load_config, save_config


class TestLoadConfig:
    def test_load_config_reads_json_dict(self) -> None:
        """load_config 读取 JSON 文件并返回 dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = {"key": "value", "nested": {"a": 1}}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)

            result = load_config(path)
            assert result == data

    def test_load_config_returns_empty_dict_when_file_missing(self) -> None:
        """load_config 文件不存在时返回空 dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            result = load_config(path)
            assert result == {}

    def test_load_config_handles_empty_file(self) -> None:
        """load_config 空文件时返回空 dict（或 json decode error 表现为空 dict 行为）."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "empty.json"
            path.write_text("", encoding="utf-8")

            # An empty file causes JSONDecodeError; the function should handle this
            result = load_config(path)
            assert result == {}


class TestSaveConfig:
    def test_save_config_writes_json_and_reloads(self) -> None:
        """save_config 写入 JSON 后 load_config 能正确读回."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = {"hello": "world", "count": 42}

            save_config(path, data)
            result = load_config(path)
            assert result == data

    def test_save_config_overwrites_existing_file(self) -> None:
        """save_config 覆盖已有文件."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            save_config(path, {"old": True})
            save_config(path, {"new": True})

            result = load_config(path)
            assert result == {"new": True}

    def test_save_config_atomic_write_does_not_corrupt_on_crash(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """save_config 使用原子写入：崩溃时原文件不被损坏."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            original_data = {"intact": True, "value": 123}
            save_config(path, original_data)

            # Simulate a crash during write by making os.replace raise
            original_replace = os.replace

            def _crashing_replace(src: str, dst: str) -> None:
                raise OSError("Simulated crash during replace")

            monkeypatch.setattr(os, "replace", _crashing_replace)

            try:
                save_config(path, {"corrupted": "should not persist"})
            except OSError:
                pass

            # Restore os.replace so we can read
            monkeypatch.setattr(os, "replace", original_replace)
            result = load_config(path)
            assert result == original_data


class TestConfigIOThreadSafety:
    def test_concurrent_reads_do_not_deadlock(self) -> None:
        """并发读取不会死锁."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "shared.json"
            save_config(path, {"shared": True})

            errors: list[Exception] = []

            def _reader() -> None:
                try:
                    load_config(path)
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=_reader) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0

    def test_concurrent_write_and_read_do_not_deadlock(self) -> None:
        """并发读写不会死锁."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "shared.json"
            save_config(path, {"counter": 0})
            errors: list[Exception] = []
            barrier = threading.Barrier(6, timeout=5)

            def _writer() -> None:
                barrier.wait()
                for i in range(10):
                    try:
                        save_config(path, {"counter": i})
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)

            def _reader() -> None:
                barrier.wait()
                for _ in range(10):
                    try:
                        load_config(path)
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)

            threads = [threading.Thread(target=_writer if i < 2 else _reader) for i in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0
