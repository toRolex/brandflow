from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from packages.runtime_adapters.base import BaseRuntimeAdapter


def test_class_inherits_from_base() -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    adapter = WindowsProdRuntimeAdapter()
    assert isinstance(adapter, BaseRuntimeAdapter)


def test_profile_name() -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    adapter = WindowsProdRuntimeAdapter()
    assert adapter.profile_name == "windows-prod"


def test_ffmpeg_path_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    monkeypatch.setenv("FFMPEG_PATH", r"C:\custom\ffmpeg.exe")
    adapter = WindowsProdRuntimeAdapter()

    with mock.patch.object(Path, "exists", return_value=True):
        result = adapter.ffmpeg_path()
    assert result == Path(r"C:\custom\ffmpeg.exe")


def test_ffmpeg_path_fallback_tools_bin(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    adapter = WindowsProdRuntimeAdapter()

    def _exists_side_effect(self: Path) -> bool:
        return "ffmpeg.exe" in str(self) and "tools" in str(self)

    with mock.patch.object(Path, "exists", autospec=True) as mock_exists:
        mock_exists.side_effect = _exists_side_effect
        result = adapter.ffmpeg_path()

    assert "ffmpeg.exe" in str(result)


def test_ffmpeg_path_fallback_chocolatey(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    adapter = WindowsProdRuntimeAdapter()

    def _exists_side_effect(self: Path) -> bool:
        if "tools/bin/ffmpeg.exe" in str(self):
            return False
        return "chocolatey" in str(self)

    with mock.patch.object(Path, "exists", autospec=True) as mock_exists:
        mock_exists.side_effect = _exists_side_effect
        result = adapter.ffmpeg_path()

    assert "chocolatey" in str(result)


def test_ffmpeg_path_all_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    adapter = WindowsProdRuntimeAdapter()

    with mock.patch.object(Path, "exists", return_value=False):
        with pytest.raises(FileNotFoundError, match="ffmpeg"):
            adapter.ffmpeg_path()


def test_ensure_tools_returns_none() -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    adapter = WindowsProdRuntimeAdapter()
    assert adapter.ensure_tools() is None


def test_attempt_root_creates_directory(tmp_path: Path) -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    adapter = WindowsProdRuntimeAdapter()
    root = adapter.attempt_root(tmp_path, "attempt-001")
    assert root == tmp_path / "attempts" / "attempt-001"
    assert root.exists()
    assert root.is_dir()


def test_build_fake_outputs(tmp_path: Path) -> None:
    from packages.runtime_adapters.windows_prod import WindowsProdRuntimeAdapter

    adapter = WindowsProdRuntimeAdapter()
    attempt_root = adapter.attempt_root(tmp_path, "attempt-002")
    paths = adapter.build_fake_outputs(attempt_root)

    names = {p.name for p in paths}
    assert names == {"script.json", "audio.mp3", "subtitles.srt", "final.mp4"}
    for p in paths:
        assert p.exists()
