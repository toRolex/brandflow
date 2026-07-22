"""Tests for the /api/health endpoint — version from pyproject.toml."""

import tomllib
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app

_HERE = Path(__file__).resolve().parent.parent.parent
_PYPROJECT = _HERE / "pyproject.toml"


def test_health_returns_version_from_pyproject() -> None:
    """GET /api/health 返回的 version 字段应与 pyproject.toml 的 [project].version 一致。"""
    with open(_PYPROJECT, "rb") as f:
        expected = tomllib.load(f)["project"]["version"]

    with TestClient(create_app()) as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["version"] == expected
