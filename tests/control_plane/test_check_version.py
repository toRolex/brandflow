"""Tests for the /api/check-version endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.control_plane._version import get_version
from apps.control_plane.app import create_app
from apps.control_plane.routes import version_check


def test_check_version_returns_expected_shape() -> None:
    """GET /api/check-version 返回 {current, latest, update_available} 结构。"""
    with TestClient(create_app()) as client:
        resp = client.get("/api/check-version")
        assert resp.status_code == 200
        data = resp.json()
        assert "current" in data
        assert "latest" in data
        assert "update_available" in data
        assert isinstance(data["current"], str)
        assert isinstance(data["latest"], str)
        assert isinstance(data["update_available"], bool)


def test_check_version_detects_new_version() -> None:
    """GitHub 有新版 tag 时返回 update_available: true。"""
    with patch("apps.control_plane.routes.version_check.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"name": "v9.9.9"}]

        with TestClient(create_app()) as client:
            resp = client.get("/api/check-version")
            data = resp.json()

    assert data["current"] == get_version()
    assert data["latest"] == "9.9.9"
    assert data["update_available"] is True


def test_check_version_silent_on_github_failure() -> None:
    """GitHub API 失败（网络异常/限流）时静默返回 update_available: false。"""
    with patch("apps.control_plane.routes.version_check.requests.get") as mock_get:
        from requests.exceptions import ConnectionError

        mock_get.side_effect = ConnectionError("mock network error")

        with TestClient(create_app()) as client:
            resp = client.get("/api/check-version")
            data = resp.json()

    assert data["latest"] == ""
    assert data["update_available"] is False


def test_check_version_no_update_when_same() -> None:
    """当前版本与最新 tag 相同时返回 update_available: false。"""
    current = get_version()
    with patch("apps.control_plane.routes.version_check.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"name": f"v{current}"}]

        with TestClient(create_app()) as client:
            resp = client.get("/api/check-version")
            data = resp.json()

    assert data["latest"] == current
    assert data["update_available"] is False


def test_update_normal_path() -> None:
    """Windows 平台 POST /api/update 返回 200 + {status: started}。"""
    version_check._update_in_progress = False
    with (
        patch("apps.control_plane.routes.version_check._is_windows", return_value=True),
        patch("apps.control_plane.routes.version_check.subprocess.Popen") as mock_popen,
    ):
        with TestClient(create_app()) as client:
            resp = client.post("/api/update")

    assert resp.status_code == 200
    assert resp.json() == {"status": "started", "log": "packaging/windows/update.log"}
    mock_popen.assert_called_once()
    version_check._update_process = None  # cleanup mock from state
    version_check._update_in_progress = False


def test_update_concurrent_blocked() -> None:
    """已有更新进程时第二次请求返回 409。"""
    version_check._update_in_progress = True
    version_check._update_process = None  # clear any stale mock from previous test
    with patch(
        "apps.control_plane.routes.version_check._is_windows", return_value=True
    ):
        with TestClient(create_app()) as client:
            resp = client.post("/api/update")

    assert resp.status_code == 409
    assert resp.json() == {"status": "in_progress"}
    version_check._update_in_progress = False  # cleanup for subsequent tests
    version_check._update_process = None


def test_update_non_windows() -> None:
    """非 Windows 平台返回可读错误。"""
    version_check._update_in_progress = False
    with patch(
        "apps.control_plane.routes.version_check._is_windows", return_value=False
    ):
        with TestClient(create_app()) as client:
            resp = client.post("/api/update")

    assert resp.status_code == 400
    data = resp.json()
    assert data["status"] == "error"
    assert "Windows" in data["message"]
    version_check._update_process = None
