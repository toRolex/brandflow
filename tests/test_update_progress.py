"""Tests for GET /api/update/status and POST /api/update progress.json integration (Issue #329)."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app, _startup_cleanup_progress
from apps.control_plane.routes import version_check

# Reusable on macOS where _progress_path() returns None.
_PROGRESS_PATH = (
    Path(__file__).resolve().parent.parent / "packaging" / "windows" / "progress.json"
)


def _reset_state():
    """Clean up globals and remove any progress.json from previous test runs."""
    version_check._update_in_progress = False
    version_check._update_process = None
    if _PROGRESS_PATH.exists():
        _PROGRESS_PATH.unlink(missing_ok=True)


def _write_progress(data: dict) -> None:
    _PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PROGRESS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


# ── GET /api/update/status ──────────────────────────────────────────


def test_status_file_missing_returns_idle(client):
    """文件不存在时返回 {status: "idle"}"""
    _reset_state()
    with patch.object(version_check, "_is_windows", return_value=True):
        resp = client.get("/api/update/status")
    assert resp.status_code == 200
    assert resp.json() == {"status": "idle"}


def test_status_file_exists_returns_full_object(client):
    """progress.json 存在时返回完整状态对象"""
    _reset_state()
    _write_progress(
        {
            "status": "running",
            "step": "git_pull",
            "step_label": "拉取最新代码",
            "percent": 5,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    with patch.object(version_check, "_is_windows", return_value=True):
        resp = client.get("/api/update/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["step"] == "git_pull"
    assert data["step_label"] == "拉取最新代码"
    assert data["percent"] == 5
    assert "error" not in data
    assert "updated_at" in data


def test_status_running_is_not_stalled_when_fresh(client):
    """running 状态且 updated_at 在 2 分钟内 → 不返回 stalled"""
    _reset_state()
    _write_progress(
        {
            "status": "running",
            "step": "uv_sync",
            "step_label": "更新 Python 依赖",
            "percent": 25,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    from datetime import datetime, timezone

    fresh_now = datetime(2026, 7, 24, 10, 1, 0, tzinfo=timezone.utc).timestamp()

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch.object(version_check, "_time") as mock_time,
    ):
        mock_time.time.return_value = fresh_now
        resp = client.get("/api/update/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert not data.get("stalled")


def test_status_running_stalled_after_2_minutes(client):
    """running 状态超过 2 分钟无变化 → 返回 stalled: true"""
    _reset_state()
    _write_progress(
        {
            "status": "running",
            "step": "uv_sync",
            "step_label": "更新 Python 依赖",
            "percent": 25,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    from datetime import datetime, timezone

    fake_now = datetime(2026, 7, 24, 10, 5, 0, tzinfo=timezone.utc).timestamp()

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch.object(version_check, "_time") as mock_time,
    ):
        mock_time.time.return_value = fake_now
        resp = client.get("/api/update/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data.get("stalled") is True


def test_status_restarting_stalled_after_2_minutes(client):
    """restarting 状态超过 2 分钟 → stalled: true"""
    _reset_state()
    _write_progress(
        {
            "status": "restarting",
            "step": "restart_cp",
            "step_label": "重启控制面",
            "percent": 95,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    from datetime import datetime, timezone

    fake_now = datetime(2026, 7, 24, 10, 5, 0, tzinfo=timezone.utc).timestamp()

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch.object(version_check, "_time") as mock_time,
    ):
        mock_time.time.return_value = fake_now
        resp = client.get("/api/update/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "restarting"
    assert data.get("stalled") is True


def test_status_done_returns_full_object(client):
    """done 状态正常返回，不带 stalled"""
    _reset_state()
    _write_progress(
        {
            "status": "done",
            "step": "done",
            "step_label": "更新完成",
            "percent": 100,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    from datetime import datetime, timezone

    fake_now = datetime(2026, 7, 24, 10, 5, 0, tzinfo=timezone.utc).timestamp()

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch.object(version_check, "_time") as mock_time,
    ):
        mock_time.time.return_value = fake_now
        resp = client.get("/api/update/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert not data.get("stalled")


# ── POST /api/update conflict detection ─────────────────────────────


def test_post_update_rejects_running_not_stalled(client):
    """progress.json status=running 且未超时 → 409"""
    _reset_state()
    _write_progress(
        {
            "status": "running",
            "step": "git_pull",
            "step_label": "拉取最新代码",
            "percent": 5,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    from datetime import datetime, timezone

    fake_now = datetime(2026, 7, 24, 10, 1, 0, tzinfo=timezone.utc).timestamp()

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch.object(version_check, "_time") as mock_time,
    ):
        mock_time.time.return_value = fake_now
        resp = client.post("/api/update")
    assert resp.status_code == 409
    assert resp.json()["status"] == "in_progress"


def test_post_update_rejects_restarting_not_stalled(client):
    """progress.json status=restarting 且未超时 → 409"""
    _reset_state()
    _write_progress(
        {
            "status": "restarting",
            "step": "restart_cp",
            "step_label": "重启控制面",
            "percent": 95,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    from datetime import datetime, timezone

    fake_now = datetime(2026, 7, 24, 10, 1, 0, tzinfo=timezone.utc).timestamp()

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch.object(version_check, "_time") as mock_time,
    ):
        mock_time.time.return_value = fake_now
        resp = client.post("/api/update")
    assert resp.status_code == 409


def test_post_update_allows_failed_retry(client):
    """progress.json status=failed 时允许重试，自动清理旧状态"""
    _reset_state()
    _write_progress(
        {
            "status": "failed",
            "step": "git_pull",
            "step_label": "拉取最新代码",
            "percent": 5,
            "error": "git pull 失败",
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch("apps.control_plane.routes.version_check.subprocess.Popen"),
    ):
        resp = client.post("/api/update")
    assert resp.status_code == 200
    assert resp.json() == {"status": "started", "log": "packaging/windows/update.log"}
    # Failed status allowed retry: old file cleaned, new initial progress written.
    data = json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
    assert data["status"] == "running"  # replaced with new initial state
    _reset_state()


def test_post_update_allows_done_retry(client):
    """progress.json status=done 时允许重试，自动清理旧状态"""
    _reset_state()
    _write_progress(
        {
            "status": "done",
            "step": "done",
            "step_label": "更新完成",
            "percent": 100,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch("apps.control_plane.routes.version_check.subprocess.Popen"),
    ):
        resp = client.post("/api/update")
    assert resp.status_code == 200
    # Done status allowed retry: old file cleaned, new initial progress written.
    data = json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
    assert data["status"] == "running"  # replaced with new initial state
    _reset_state()


def test_post_update_writes_initial_progress(client):
    """POST /api/update 启动 update.bat 前写入初始 progress.json"""
    _reset_state()

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch("apps.control_plane.routes.version_check.subprocess.Popen"),
    ):
        resp = client.post("/api/update")
    assert resp.status_code == 200
    assert _PROGRESS_PATH.exists()
    data = json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
    assert data["status"] == "running"
    assert data["step"] == "git_pull"
    assert "updated_at" in data
    _reset_state()


def test_post_update_non_windows_unchanged(client):
    """非 Windows 平台返回 400 的行为不变"""
    _reset_state()
    with patch.object(version_check, "_is_windows", return_value=False):
        resp = client.post("/api/update")
    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    _reset_state()


def test_post_update_in_memory_lock_unchanged(client):
    """_update_in_progress 内存锁仍然生效"""
    _reset_state()
    version_check._update_in_progress = True
    with patch.object(version_check, "_is_windows", return_value=True):
        resp = client.post("/api/update")
    assert resp.status_code == 409
    assert resp.json()["status"] == "in_progress"
    _reset_state()


# ── Startup cleanup (lifespan) ──────────────────────────────────────


def test_startup_cleanup_stale_running():
    """启动时 running 超过 5 分钟 → 重置锁 + 清理文件"""
    _reset_state()
    version_check._update_in_progress = True
    _write_progress(
        {
            "status": "running",
            "step": "git_pull",
            "step_label": "拉取最新代码",
            "percent": 5,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    from datetime import datetime, timezone

    fake_now = datetime(2026, 7, 24, 10, 10, 0, tzinfo=timezone.utc).timestamp()

    with (
        patch.object(version_check, "_is_windows", return_value=True),
        patch.object(version_check, "_time") as mock_time,
    ):
        mock_time.time.return_value = fake_now
        _startup_cleanup_progress()

    assert version_check._update_in_progress is False
    assert not _PROGRESS_PATH.exists()


def test_startup_cleanup_done_state():
    """启动时 done 状态直接清理（不阻塞下次更新）"""
    _reset_state()
    _write_progress(
        {
            "status": "done",
            "step": "done",
            "step_label": "更新完成",
            "percent": 100,
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    with patch.object(version_check, "_is_windows", return_value=True):
        _startup_cleanup_progress()
    assert not _PROGRESS_PATH.exists()


def test_startup_cleanup_failed_state():
    """启动时 failed 状态直接清理"""
    _reset_state()
    _write_progress(
        {
            "status": "failed",
            "step": "git_pull",
            "step_label": "拉取最新代码",
            "percent": 5,
            "error": "git pull 失败",
            "updated_at": "2026-07-24T10:00:00+00:00",
        }
    )

    with patch.object(version_check, "_is_windows", return_value=True):
        _startup_cleanup_progress()
    assert not _PROGRESS_PATH.exists()


def test_startup_cleanup_no_file():
    """progress.json 不存在时无操作"""
    _reset_state()
    with patch.object(version_check, "_is_windows", return_value=True):
        _startup_cleanup_progress()
    assert version_check._update_in_progress is False
