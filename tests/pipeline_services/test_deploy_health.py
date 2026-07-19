from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


from packages.deploy_health.checker import (
    DeployHealthChecker,
    DeployHealthResult,
)


class TestDeployHealthCheckerCheckTools:
    def test_all_tools_available(self):
        """当所有工具都可用时，全部返回 pass。"""
        checker = DeployHealthChecker(root_dir=Path("/tmp"))
        with (
            patch(
                "packages.pipeline_services.media_utils._resolve_ffmpeg_path",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_ffprobe_path",
                return_value="/usr/bin/ffprobe",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_whisper_cli_path",
                return_value="/usr/bin/whisper-cli",
            ),
        ):
            results = checker._check_tools()
        assert all(r.status == "pass" for r in results)
        assert len(results) == 3

    def test_ffmpeg_missing_reports_fail(self):
        """缺少 ffmpeg 时返回 fail 及修复建议。"""
        checker = DeployHealthChecker(root_dir=Path("/tmp"))
        with (
            patch(
                "packages.pipeline_services.media_utils._resolve_ffmpeg_path",
                return_value=None,
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_ffprobe_path",
                return_value="/usr/bin/ffprobe",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_whisper_cli_path",
                return_value="/usr/bin/whisper-cli",
            ),
        ):
            results = checker._check_tools()
        ffmpeg = [r for r in results if r.name == "ffmpeg"][0]
        assert ffmpeg.status == "fail"
        assert ffmpeg.fix is not None

    def test_uses_media_utils_for_path_resolution(self):
        """_check_tools 应复用 media_utils 的 _resolve_ffmpeg_path 解析路径。"""
        checker = DeployHealthChecker(root_dir=Path("/tmp"))
        with (
            patch(
                "packages.pipeline_services.media_utils._resolve_ffmpeg_path",
                return_value="/custom/ffmpeg",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_ffprobe_path",
                return_value="/custom/ffprobe",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_whisper_cli_path",
                return_value="/custom/whisper-cli",
            ),
        ):
            results = checker._check_tools()
        ffmpeg_result = [r for r in results if r.name == "ffmpeg"][0]
        assert "/custom/ffmpeg" in ffmpeg_result.message


class TestDeployHealthCheckerCheckDirectories:
    def test_workspace_exists(self, tmp_path):
        """workspace 目录存在时返回 pass。"""
        (tmp_path / "workspace").mkdir()
        checker = DeployHealthChecker(root_dir=tmp_path)
        results = checker._check_directories()
        ws = [r for r in results if r.name == "workspace 目录"][0]
        assert ws.status == "pass"

    def test_workspace_missing_creatable(self, tmp_path):
        """workspace 目录不存在但父目录可写时返回 warn。"""
        checker = DeployHealthChecker(root_dir=tmp_path)
        results = checker._check_directories()
        ws = [r for r in results if r.name == "workspace 目录"][0]
        assert ws.status in ("warn", "pass")

    def test_config_exists(self, tmp_path):
        """config/app_config.json 存在时返回 pass。"""
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "app_config.json").write_text("{}")
        checker = DeployHealthChecker(root_dir=tmp_path)
        results = checker._check_directories()
        cfg = [r for r in results if r.name == "app_config.json"][0]
        assert cfg.status == "pass"

    def test_config_missing(self, tmp_path):
        """config/app_config.json 不存在时返回 warn（应用启动时自动创建）。"""
        checker = DeployHealthChecker(root_dir=tmp_path)
        results = checker._check_directories()
        cfg = [r for r in results if r.name == "app_config.json"][0]
        assert cfg.status == "warn"


class TestDeployHealthCheckerCheckPorts:
    def test_port_free(self):
        """端口未被占用时返回 pass（实际绑定测试可能因权限失败，用 mock）。"""
        checker = DeployHealthChecker(root_dir=Path("/tmp"))
        with patch("socket.socket") as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.bind.return_value = None
            mock_sock.setsockopt.return_value = None
            results = checker._check_ports()
        p17890 = [r for r in results if r.name == "端口 17890"][0]
        assert p17890.status == "pass"

    def test_port_in_use(self):
        """端口被占用时返回 fail。"""
        checker = DeployHealthChecker(root_dir=Path("/tmp"))
        with patch("socket.socket") as mock_socket_class:
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.bind.side_effect = OSError(48, "Address already in use")
            mock_sock.setsockopt.return_value = None
            results = checker._check_ports()
        p17890 = [r for r in results if r.name == "端口 17890"][0]
        assert p17890.status == "fail"


class TestDeployHealthCheckerCheckAll:
    def test_check_all_returns_deploy_health_result(self, tmp_path):
        """check_all 返回 DeployHealthResult 包含所有检查项。"""
        (tmp_path / "workspace").mkdir()
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "app_config.json").write_text("{}")
        checker = DeployHealthChecker(root_dir=tmp_path)
        with (
            patch(
                "packages.pipeline_services.media_utils._resolve_ffmpeg_path",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_ffprobe_path",
                return_value="/usr/bin/ffprobe",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_whisper_cli_path",
                return_value="/usr/bin/whisper-cli",
            ),
            patch("socket.socket") as mock_socket_class,
        ):
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.bind.return_value = None
            mock_sock.setsockopt.return_value = None
            result = checker.check_all()
        assert isinstance(result, DeployHealthResult)
        assert len(result.tools) >= 2
        assert len(result.directories) > 0
        assert len(result.ports) >= 2
        assert result.overall in ("healthy", "degraded", "unhealthy")

    def test_check_all_overall_healthy(self, tmp_path):
        """所有检查通过时 overall 为 healthy。"""
        (tmp_path / "workspace").mkdir()
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "app_config.json").write_text("{}")
        checker = DeployHealthChecker(root_dir=tmp_path)
        with (
            patch(
                "packages.pipeline_services.media_utils._resolve_ffmpeg_path",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_ffprobe_path",
                return_value="/usr/bin/ffprobe",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_whisper_cli_path",
                return_value="/usr/bin/whisper-cli",
            ),
            patch("socket.socket") as mock_socket_class,
        ):
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.bind.return_value = None
            mock_sock.setsockopt.return_value = None
            result = checker.check_all()
        assert result.overall == "healthy"

    def test_check_all_overall_unhealthy(self, tmp_path):
        """有工具缺失时 overall 为 unhealthy。"""
        (tmp_path / "workspace").mkdir()
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "app_config.json").write_text("{}")
        checker = DeployHealthChecker(root_dir=tmp_path)
        with (
            patch(
                "packages.pipeline_services.media_utils._resolve_ffmpeg_path",
                return_value=None,
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_ffprobe_path",
                return_value="/usr/bin/ffprobe",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_whisper_cli_path",
                return_value="/usr/bin/whisper-cli",
            ),
            patch("socket.socket") as mock_socket_class,
        ):
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.bind.return_value = None
            mock_sock.setsockopt.return_value = None
            result = checker.check_all()
        assert result.overall == "unhealthy"

    def test_check_all_serializable(self, tmp_path):
        """check_all 结果可 JSON 序列化。"""
        (tmp_path / "workspace").mkdir()
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "app_config.json").write_text("{}")
        checker = DeployHealthChecker(root_dir=tmp_path)
        with (
            patch(
                "packages.pipeline_services.media_utils._resolve_ffmpeg_path",
                return_value="/usr/bin/ffmpeg",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_ffprobe_path",
                return_value="/usr/bin/ffprobe",
            ),
            patch(
                "packages.pipeline_services.media_utils._resolve_whisper_cli_path",
                return_value="/usr/bin/whisper-cli",
            ),
            patch("socket.socket") as mock_socket_class,
        ):
            mock_sock = MagicMock()
            mock_socket_class.return_value = mock_sock
            mock_sock.bind.return_value = None
            mock_sock.setsockopt.return_value = None
            result = checker.check_all()
        data = result.to_dict()
        json_str = json.dumps(data, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["overall"] == "healthy"
        assert isinstance(parsed["tools"], list)
        assert isinstance(parsed["directories"], list)
        assert isinstance(parsed["ports"], list)
