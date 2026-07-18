from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from packages.runtime_adapters.adapter import RuntimeAdapter


class TestProfileName:
    def test_default_profile(self) -> None:
        assert RuntimeAdapter().profile_name == "mac-local"

    def test_custom_profile(self) -> None:
        assert RuntimeAdapter("windows-prod").profile_name == "windows-prod"


class TestFfmpegPath:
    def test_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FFMPEG_PATH", "/opt/ffmpeg/bin/ffmpeg")
        with mock.patch.object(Path, "exists", return_value=True):
            result = RuntimeAdapter().ffmpeg_path()
        assert result == Path("/opt/ffmpeg/bin/ffmpeg")

    def test_tools_bin(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FFMPEG_PATH", raising=False)

        def _exists_side_effect(self: Path) -> bool:
            return "ffmpeg" in str(self) and "tools" in str(self) and "bin" in str(self)

        with (
            mock.patch.object(Path, "exists", autospec=True) as mock_exists,
            mock.patch("shutil.which", return_value=None),
        ):
            mock_exists.side_effect = _exists_side_effect
            result = RuntimeAdapter().ffmpeg_path()

        assert "ffmpeg" in str(result)
        assert "tools" in str(result)

    def test_shutil_which(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        with (
            mock.patch.object(Path, "exists", return_value=False),
            mock.patch("shutil.which", return_value="/usr/local/bin/ffmpeg"),
        ):
            result = RuntimeAdapter().ffmpeg_path()
        assert result == Path("/usr/local/bin/ffmpeg")

    def test_all_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        with (
            mock.patch.object(Path, "exists", return_value=False),
            mock.patch("shutil.which", return_value=None),
        ):
            with pytest.raises(FileNotFoundError, match="ffmpeg"):
                RuntimeAdapter().ffmpeg_path()


def test_ensure_tools_returns_none() -> None:
    assert RuntimeAdapter().ensure_tools() is None


def test_attempt_root_creates_directory(tmp_path: Path) -> None:
    root = RuntimeAdapter().attempt_root(tmp_path, "attempt-001")
    assert root == tmp_path / "attempts" / "attempt-001"
    assert root.exists()


def test_build_fake_outputs(tmp_path: Path) -> None:
    adapter = RuntimeAdapter()
    attempt = adapter.attempt_root(tmp_path, "attempt-002")
    paths = adapter.build_fake_outputs(attempt)
    names = {p.name for p in paths}
    assert names == {"script.json", "audio.mp3", "subtitles.srt", "final.mp4"}
    for p in paths:
        assert p.exists()
