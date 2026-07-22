"""Test: update.bat 清理验证（预重构）

验证三个 seam：
1. 无 pause 命令残留
2. 所有输出重定向到 update.log
3. exit code 正确透传
"""

import os

BAT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "packaging", "windows", "update.bat"
)


def _read_bat() -> str:
    with open(os.path.abspath(BAT_PATH), encoding="utf-8") as f:
        return f.read()


def test_no_pause_command():
    """Seam 1: update.bat 中无 pause 残留"""
    content = _read_bat()
    # 过滤注释行中的 pause 说明（如果存在）
    lines = [x for x in content.splitlines() if not x.strip().startswith("::")]
    for i, line in enumerate(lines, 1):
        assert "pause" not in line, f"Line {i} contains 'pause': {line.strip()}"


def test_log_redirection():
    """Seam 2: 所有 stdout/stderr 重定向到 update.log 或全局日志"""
    content = _read_bat()
    # 日志重定向应在脚本中有一致路径
    assert "update.log" in content, "update.log 未出现在脚本中"


def test_exit_code_propagation():
    """Seam 3: exit code 正确透传"""
    content = _read_bat()
    # 所有 exit /b 应使用 %errorlevel%
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("exit"):
            assert "%errorlevel%" in stripped, (
                f"Line {i}: exit 硬编码而非 %errorlevel%: {stripped}"
            )
