"""Tests for media_utils path resolvers."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from packages.pipeline_services.media_utils import (
    ToolNotFoundError,
    _resolve_ffmpeg_path,
    _resolve_ffprobe_path,
    _resolve_whisper_cli_path,
)


class TestResolveFfmpegPath:
    def test_env_var_absolute_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        executable = tmp_path / "custom_ffmpeg"
        executable.write_text("")
        monkeypatch.setenv("FFMPEG_PATH", str(executable))

        result = _resolve_ffmpeg_path()
        assert result == str(executable)

    def test_env_var_command_in_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FFMPEG_PATH", "ffmpeg")

        with mock.patch("shutil.which", return_value="/usr/bin/ffmpeg") as mock_which:
            result = _resolve_ffmpeg_path()

        assert result == "ffmpeg"
        mock_which.assert_called_once_with("ffmpeg")

    def test_tools_bin_candidate(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        executable = tmp_path / "tools" / "bin" / "ffmpeg"
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text("")

        with mock.patch("pathlib.Path.cwd", return_value=tmp_path):
            result = _resolve_ffmpeg_path()

        assert result == str(executable)

    def test_shutil_which_fallback(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("FFMPEG_PATH", raising=False)

        with (
            mock.patch("pathlib.Path.cwd", return_value=tmp_path),
            mock.patch("shutil.which", return_value="/usr/local/bin/ffmpeg"),
        ):
            result = _resolve_ffmpeg_path()

        assert result == "/usr/local/bin/ffmpeg"

    def test_not_found_raises_tool_not_found_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("FFMPEG_PATH", raising=False)

        with (
            mock.patch("pathlib.Path.cwd", return_value=tmp_path),
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch("shutil.which", return_value=None),
        ):
            with pytest.raises(ToolNotFoundError, match="ffmpeg not found") as exc_info:
                _resolve_ffmpeg_path()

        error = exc_info.value
        assert error.tool_name == "ffmpeg"
        assert any("tools/bin/ffmpeg" in path for path in error.attempted)
        assert "FFMPEG_PATH" in error.suggestion


class TestResolveFfprobePath:
    def test_env_var_absolute_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        executable = tmp_path / "custom_ffprobe"
        executable.write_text("")
        monkeypatch.setenv("FFPROBE_PATH", str(executable))

        result = _resolve_ffprobe_path()
        assert result == str(executable)

    def test_not_found_raises_tool_not_found_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("FFPROBE_PATH", raising=False)

        with (
            mock.patch("pathlib.Path.cwd", return_value=tmp_path),
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch("shutil.which", return_value=None),
        ):
            with pytest.raises(
                ToolNotFoundError, match="ffprobe not found"
            ) as exc_info:
                _resolve_ffprobe_path()

        assert exc_info.value.tool_name == "ffprobe"


class TestResolveWhisperCliPath:
    def test_env_var_absolute_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        executable = tmp_path / "custom_whisper"
        executable.write_text("")
        monkeypatch.setenv("WHISPER_CLI_PATH", str(executable))

        result = _resolve_whisper_cli_path()
        assert result == str(executable)

    def test_not_found_raises_tool_not_found_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("WHISPER_CLI_PATH", raising=False)

        with (
            mock.patch("pathlib.Path.cwd", return_value=tmp_path),
            mock.patch("pathlib.Path.exists", return_value=False),
            mock.patch("shutil.which", return_value=None),
        ):
            with pytest.raises(
                ToolNotFoundError, match="whisper-cli not found"
            ) as exc_info:
                _resolve_whisper_cli_path()

        assert exc_info.value.tool_name == "whisper-cli"
