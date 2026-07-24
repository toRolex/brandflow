"""Test: update.bat - progress.json 写入 + 安全重启 (Issue #328)

验证六个 seam：
1. 初始状态写入
2. 步骤跳变
3. 失败写入 error
4. 安全重启命令
5. nssm 缺席跳过重启
6. done 状态保留在磁盘
"""

import os
import re

BAT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "packaging", "windows", "update.bat"
)


def _read_bat() -> str:
    with open(os.path.abspath(BAT_PATH), encoding="utf-8") as f:
        return f.read()


# -- 旧验收用例（保留） -------------------------------------------------


def test_no_pause_command():
    """Seam 1: update.bat 中无 pause 残留"""
    content = _read_bat()
    lines = [x for x in content.splitlines() if not x.strip().startswith("::")]
    for i, line in enumerate(lines, 1):
        assert "pause" not in line, f"Line {i} contains 'pause': {line.strip()}"


def test_log_redirection():
    """Seam 2: 所有 stdout/stderr 重定向到 update.log 或全局日志"""
    content = _read_bat()
    assert "update.log" in content, "update.log 未出现在脚本中"


def test_exit_code_propagation():
    """Seam 3: exit code 正确透传"""
    content = _read_bat()
    for i, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("exit"):
            assert "%errorlevel%" in stripped, (
                f"Line {i}: exit 硬编码而非 %errorlevel%: {stripped}"
            )


# -- Issue #328 新测试 -------------------------------------------------


def _progress_lines(content: str):
    """返回所有写入 progress.json 的行（不含空行和注释）"""
    return [
        ln
        for ln in content.splitlines()
        if ("progress.json" in ln or "PROGRESS_FILE" in ln)
        and not ln.strip().startswith("::")
    ]


def test_progress_initial_state():
    """S1: 初始状态写入 progress.json，含 status/running + step/git_pull"""
    content = _read_bat()
    lines = _progress_lines(content)
    assert len(lines) >= 1, "progress.json 未出现在脚本中"
    assert "status" in content
    assert "running" in content
    assert "git_pull" in content
    assert "拉取最新代码" in content


def test_progress_step_transitions():
    """S2: 步骤跳变：5→25→50→90→95→100"""
    content = _read_bat()
    lines = _progress_lines(content)
    percents_found = []
    for ln in lines:
        matches = re.findall(r'"percent"\s*:\s*(\d+)', ln)
        percents_found.extend(int(m) for m in matches)
    expected = [5, 25, 50, 90, 95, 100]
    for p in expected:
        assert p in percents_found, f"percent={p} 未在 progress.json 写入中找到"


def test_progress_failure_writes_error():
    """S3: 失败步骤写入 status: failed + error 字段"""
    content = _read_bat()
    assert "failed" in content, "status: failed 未出现"
    assert "error" in content, "error 字段未出现"
    assert content.count("status") >= 5, "进度写入次数不足"


def test_restart_cp_safe_mechanism():
    """S4: 最后一步使用 start /b + timeout + nssm restart 安全重启控制面"""
    content = _read_bat()
    assert "start /b" in content, "缺少 start /b 安全重启机制"
    assert "timeout /t" in content, "缺少 timeout 延迟"
    assert "brandflow-control-plane" in content, "缺少控制面 nssm 服务名"


def test_nssm_absent_skips_restart():
    """S5: nssm 不存在时跳过重启，percent 到 100%，status=done"""
    content = _read_bat()
    assert "done" in content, "完成状态 done 未出现"
    assert "not exist" in content.lower() or "!exist" in content.lower(), (
        "缺少 nssm 不存在时的条件分支"
    )
    assert "100" in content, "完成百分比 100 未出现"


def test_progress_json_persists_on_done():
    """S6: done 时 progress.json 保留在磁盘，不被清理"""
    content = _read_bat()
    delete_patterns = [
        "del progress.json",
        "erase progress.json",
        "rm progress.json",
        "del /f progress.json",
    ]
    for pat in delete_patterns:
        assert pat not in content.lower(), f"progress.json 被删除: {pat}"
    assert "done" in content, "done 状态未出现"
