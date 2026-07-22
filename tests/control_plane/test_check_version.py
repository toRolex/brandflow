"""Tests for the /api/check-version endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.control_plane._version import get_version
from apps.control_plane.app import create_app


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
