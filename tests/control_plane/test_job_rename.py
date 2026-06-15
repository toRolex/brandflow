"""Tests for job rename functionality."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    """创建带临时目录的测试客户端。"""
    from apps.control_plane.app import create_app

    app = create_app(root_dir=tmp_path)
    with TestClient(app) as c:
        yield c


def test_rename_job_returns_404_for_missing_job(client):
    """不存在的 job 应返回 404。"""
    response = client.put(
        "/api/jobs/nonexistent_job_id/rename",
        json={"name": "新名称"},
    )
    assert response.status_code == 404


def test_create_job_accepts_name(client):
    """创建 job 时应接受并返回 name 字段。"""
    response = client.post(
        "/api/projects/test-proj/jobs",
        json={
            "product": "荔枝菌",
            "platforms": ["抖音"],
            "name": "我的自定义名称",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("name") == "我的自定义名称"
