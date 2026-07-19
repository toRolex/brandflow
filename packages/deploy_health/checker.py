"""部署体检：启动前检查外部工具、端口、配置和工作目录。"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CheckItem:
    """单条检查结果。"""

    name: str
    status: str  # "pass" | "fail" | "warn"
    message: str
    fix: str | None = None


@dataclass
class DeployHealthResult:
    """完整部署体检结果。"""

    tools: list[CheckItem] = field(default_factory=list)
    directories: list[CheckItem] = field(default_factory=list)
    ports: list[CheckItem] = field(default_factory=list)
    overall: str = "healthy"  # "healthy" | "degraded" | "unhealthy"

    def to_dict(self) -> dict[str, Any]:
        def _item(d: CheckItem) -> dict[str, Any]:
            result: dict[str, Any] = {
                "name": d.name,
                "status": d.status,
                "message": d.message,
            }
            if d.fix:
                result["fix"] = d.fix
            return result

        return {
            "tools": [_item(t) for t in self.tools],
            "directories": [_item(d) for d in self.directories],
            "ports": [_item(p) for p in self.ports],
            "overall": self.overall,
        }


class DeployHealthChecker:
    """部署体检器。

    检查项：
    - 外部工具：ffmpeg / ffprobe / whisper-cli
    - 目录与文件：config/app_config.json / workspace / logs / 素材目录
    - 端口：17890（后端）/ 5173（前端）
    """

    BACKEND_PORT = 17890
    FRONTEND_PORT = 5173

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = Path(root_dir)

    def check_all(self) -> DeployHealthResult:
        """运行所有检查并返回结构化结果。"""
        tools = self._check_tools()
        dirs = self._check_directories()
        ports = self._check_ports()

        all_items = tools + dirs + ports
        fail_count = sum(1 for i in all_items if i.status == "fail")

        if fail_count == 0:
            overall = "healthy"
        elif any(i.status == "fail" for i in tools):
            # 工具缺失是最严重的
            overall = "unhealthy"
        else:
            overall = "degraded"

        return DeployHealthResult(
            tools=tools,
            directories=dirs,
            ports=ports,
            overall=overall,
        )

    def _check_tools(self) -> list[CheckItem]:
        """检查外部工具可执行性。

        复用 media_utils 的 ``_resolve_ffmpeg_path`` / ``_resolve_ffprobe_path`` /
        ``_resolve_whisper_cli_path`` 解析实际可执行路径。
        """
        from packages.pipeline_services.media_utils import (
            _resolve_ffmpeg_path,
            _resolve_ffprobe_path,
            _resolve_whisper_cli_path,
        )

        results: list[CheckItem] = []
        fixes = {
            "ffmpeg": "请安装 ffmpeg: https://ffmpeg.org/download.html 或 'brew install ffmpeg' / 'apt install ffmpeg'",
            "ffprobe": "ffprobe 通常随 ffmpeg 一起安装。请安装 ffmpeg: https://ffmpeg.org/download.html",
            "whisper-cli": "请安装 whisper-cpp: https://github.com/ggerganov/whisper.cpp",
        }

        for name, resolver in (
            ("ffmpeg", _resolve_ffmpeg_path),
            ("ffprobe", _resolve_ffprobe_path),
            ("whisper-cli", _resolve_whisper_cli_path),
        ):
            resolved = resolver()
            if resolved:
                results.append(
                    CheckItem(
                        name=name,
                        status="pass",
                        message=f"已找到: {resolved}",
                    )
                )
            else:
                results.append(
                    CheckItem(
                        name=name,
                        status="fail",
                        message=f"未找到可执行文件: {name}",
                        fix=fixes.get(name),
                    )
                )

        return results

    def _check_directories(self) -> list[CheckItem]:
        """检查关键目录和文件是否存在或可创建。"""
        results: list[CheckItem] = []

        # config/app_config.json
        config_path = self._root_dir / "config" / "app_config.json"
        if config_path.exists():
            results.append(
                CheckItem(
                    name="app_config.json",
                    status="pass",
                    message=f"已存在: {config_path}",
                )
            )
        else:
            # 检查 config 目录是否存在或可创建
            config_dir = config_path.parent
            if config_dir.exists():
                results.append(
                    CheckItem(
                        name="app_config.json",
                        status="warn",
                        message=f"配置文件不存在: {config_path}（将以默认配置运行）",
                        fix="运行应用后将自动生成默认配置文件",
                    )
                )
            else:
                results.append(
                    CheckItem(
                        name="app_config.json",
                        status="warn",
                        message=f"config 目录不存在: {config_dir}",
                        fix="运行应用后将自动创建 config 目录和默认配置",
                    )
                )

        # workspace 目录
        workspace = self._root_dir / "workspace"
        if workspace.exists() and workspace.is_dir():
            results.append(
                CheckItem(
                    name="workspace 目录",
                    status="pass",
                    message=f"已存在: {workspace}",
                )
            )
        else:
            parent = workspace.parent
            if parent.exists() and os.access(str(parent), os.W_OK):
                results.append(
                    CheckItem(
                        name="workspace 目录",
                        status="warn",
                        message=f"不存在: {workspace}（首次运行将自动创建）",
                    )
                )
            else:
                results.append(
                    CheckItem(
                        name="workspace 目录",
                        status="fail",
                        message=f"无法创建 workspace 目录: {workspace}",
                        fix=f"请确保 {parent} 目录可写",
                    )
                )

        # logs 目录
        logs = self._root_dir / "logs"
        if logs.exists() and logs.is_dir():
            results.append(
                CheckItem(
                    name="logs 目录",
                    status="pass",
                    message=f"已存在: {logs}",
                )
            )
        else:
            parent = logs.parent
            if parent.exists() and os.access(str(parent), os.W_OK):
                results.append(
                    CheckItem(
                        name="logs 目录",
                        status="warn",
                        message=f"不存在: {logs}（首次运行将自动创建）",
                    )
                )
            else:
                results.append(
                    CheckItem(
                        name="logs 目录",
                        status="fail",
                        message=f"无法创建 logs 目录: {logs}",
                        fix=f"请确保 {parent} 目录可写",
                    )
                )

        # 素材目录（通过环境变量或默认值）
        material_dir = os.getenv(
            "MATERIAL_DIR",
            str(self._root_dir / "workspace" / "materials"),
        )
        mat_path = Path(material_dir)
        if mat_path.exists() and mat_path.is_dir():
            results.append(
                CheckItem(
                    name="素材目录",
                    status="pass",
                    message=f"已存在: {mat_path}",
                )
            )
        else:
            results.append(
                CheckItem(
                    name="素材目录",
                    status="warn",
                    message=f"不存在: {mat_path}",
                    fix="请设置 MATERIAL_DIR 环境变量或创建该目录",
                )
            )

        return results

    def _check_ports(self) -> list[CheckItem]:
        """检查后端和前端端口是否被占用。"""
        results: list[CheckItem] = []
        ports = [
            (self.BACKEND_PORT, "后端"),
            (self.FRONTEND_PORT, "前端"),
        ]

        for port, label in ports:
            name = f"端口 {port}"
            if _is_port_available(port):
                results.append(
                    CheckItem(
                        name=name,
                        status="pass",
                        message=f"{label}端口 {port} 可用",
                    )
                )
            else:
                fix = (
                    f"请释放端口 {port}，或设置 PORT 环境变量更换端口"
                    if port == self.BACKEND_PORT
                    else f"请释放端口 {port}"
                )
                results.append(
                    CheckItem(
                        name=name,
                        status="fail",
                        message=f"{label}端口 {port} 已被占用",
                        fix=fix,
                    )
                )

        return results


def _is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """检查端口是否可用（尝试绑定）。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()
