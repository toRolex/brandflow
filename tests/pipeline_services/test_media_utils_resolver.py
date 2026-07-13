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
    get_whisper_cli_path,
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


class TestResolveFfmpegPathWithConfig:
    """Tests for _resolve_ffmpeg_path with ConfigReader support (Issue #88)."""

    def test_config_path_takes_priority_over_tools_bin(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """config media.ffmpeg_path should be tried before tools/bin/."""
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        config_exe = tmp_path / "opt" / "myffmpeg"
        config_exe.parent.mkdir(parents=True, exist_ok=True)
        config_exe.write_text("")

        fake_reader = mock.Mock()
        fake_reader.get_media_config.return_value = {"ffmpeg_path": str(config_exe)}

        # tools/bin/ffmpeg does NOT exist, shutil.which returns None
        with (
            mock.patch("pathlib.Path.cwd", return_value=tmp_path),
            mock.patch("shutil.which", return_value=None),
        ):
            result = _resolve_ffmpeg_path(reader=fake_reader)

        assert result == str(config_exe)

    def test_env_var_still_wins_over_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """env var FFMPEG_PATH must still beat app_config.json."""
        env_exe = tmp_path / "env_ffmpeg"
        env_exe.write_text("")
        monkeypatch.setenv("FFMPEG_PATH", str(env_exe))

        config_exe = tmp_path / "config_ffmpeg"
        config_exe.write_text("")

        fake_reader = mock.Mock()
        fake_reader.get_media_config.return_value = {"ffmpeg_path": str(config_exe)}

        result = _resolve_ffmpeg_path(reader=fake_reader)
        assert result == str(env_exe)

    def test_config_path_not_exists_falls_through(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """If config path does not exist on disk, fall through to tools/bin/."""
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        tools_exe = tmp_path / "tools" / "bin" / "ffmpeg"
        tools_exe.parent.mkdir(parents=True, exist_ok=True)
        tools_exe.write_text("")

        fake_reader = mock.Mock()
        fake_reader.get_media_config.return_value = {
            "ffmpeg_path": "/nonexistent/ffmpeg"
        }

        with mock.patch("pathlib.Path.cwd", return_value=tmp_path):
            result = _resolve_ffmpeg_path(reader=fake_reader)

        assert result == str(tools_exe)

    def test_no_reader_backward_compatible(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Calling without reader should work as before (no config step)."""
        monkeypatch.delenv("FFMPEG_PATH", raising=False)
        tools_exe = tmp_path / "tools" / "bin" / "ffmpeg"
        tools_exe.parent.mkdir(parents=True, exist_ok=True)
        tools_exe.write_text("")

        with mock.patch("pathlib.Path.cwd", return_value=tmp_path):
            result = _resolve_ffmpeg_path()

        assert result == str(tools_exe)


class TestResolveFfprobePathWithConfig:
    """Tests for _resolve_ffprobe_path with ConfigReader support (Issue #88)."""

    def test_config_path_resolved(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("FFPROBE_PATH", raising=False)
        config_exe = tmp_path / "opt" / "myffprobe"
        config_exe.parent.mkdir(parents=True, exist_ok=True)
        config_exe.write_text("")

        fake_reader = mock.Mock()
        fake_reader.get_media_config.return_value = {"ffprobe_path": str(config_exe)}

        with (
            mock.patch("pathlib.Path.cwd", return_value=tmp_path),
            mock.patch("shutil.which", return_value=None),
        ):
            result = _resolve_ffprobe_path(reader=fake_reader)

        assert result == str(config_exe)

    def test_env_var_wins_over_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("FFPROBE_PATH", str(tmp_path / "env_ffprobe"))
        (tmp_path / "env_ffprobe").write_text("")

        fake_reader = mock.Mock()
        fake_reader.get_media_config.return_value = {
            "ffprobe_path": "/nonexistent/ffprobe"
        }

        result = _resolve_ffprobe_path(reader=fake_reader)
        assert result == str(tmp_path / "env_ffprobe")


class TestResolveWhisperCliPathWithConfig:
    """Tests for _resolve_whisper_cli_path with ConfigReader support (Issue #88)."""

    def test_config_path_resolved(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("WHISPER_CLI_PATH", raising=False)
        config_exe = tmp_path / "opt" / "mywhisper"
        config_exe.parent.mkdir(parents=True, exist_ok=True)
        config_exe.write_text("")

        fake_reader = mock.Mock()
        fake_reader.get_media_config.return_value = {"whisper_cli_path": str(config_exe)}

        with (
            mock.patch("pathlib.Path.cwd", return_value=tmp_path),
            mock.patch("shutil.which", return_value=None),
        ):
            result = _resolve_whisper_cli_path(reader=fake_reader)

        assert result == str(config_exe)

    def test_env_var_wins_over_config(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("WHISPER_CLI_PATH", str(tmp_path / "env_whisper"))
        (tmp_path / "env_whisper").write_text("")

        fake_reader = mock.Mock()
        fake_reader.get_media_config.return_value = {
            "whisper_cli_path": "/nonexistent/whisper"
        }

        result = _resolve_whisper_cli_path(reader=fake_reader)
        assert result == str(tmp_path / "env_whisper")


class TestGetWhisperCliPath:
    """Tests for the public get_whisper_cli_path function."""

    def test_delegates_to_resolve_with_reader(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """get_whisper_cli_path(reader) should delegate to _resolve_whisper_cli_path."""
        monkeypatch.delenv("WHISPER_CLI_PATH", raising=False)
        config_exe = tmp_path / "opt" / "whisper_from_config"
        config_exe.parent.mkdir(parents=True, exist_ok=True)
        config_exe.write_text("")

        fake_reader = mock.Mock()
        fake_reader.get_media_config.return_value = {"whisper_cli_path": str(config_exe)}

        with (
            mock.patch("pathlib.Path.cwd", return_value=tmp_path),
            mock.patch("shutil.which", return_value=None),
        ):
            result = get_whisper_cli_path(reader=fake_reader)

        assert result == str(config_exe)

    def test_no_reader_falls_through_to_tools_bin(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """get_whisper_cli_path() without reader should use tools/bin/ fallback."""
        monkeypatch.delenv("WHISPER_CLI_PATH", raising=False)
        tools_exe = tmp_path / "tools" / "bin" / "whisper-cli"
        tools_exe.parent.mkdir(parents=True, exist_ok=True)
        tools_exe.write_text("")

        with mock.patch("pathlib.Path.cwd", return_value=tmp_path):
            result = get_whisper_cli_path()

        assert result == str(tools_exe)
