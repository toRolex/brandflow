from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


class TestProductConfigAPI:
    """/api/config/product CRUD"""

    def test_get_defaults(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/api/config/product")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_name"] == ""
        assert data["default_brand"] == ""
        assert "script" in data
        assert data["script"]["word_count_min"] == 150
        assert data["script"]["word_count_max"] == 200

    def test_put_updates_config(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.put(
            "/api/config/product",
            json={"default_name": "测试产品", "default_brand": "测试品牌"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_name"] == "测试产品"
        assert data["default_brand"] == "测试品牌"

    def test_put_deep_merge(self, tmp_path: Path) -> None:
        """PUT 只更新传入的字段，其他保留 DEFAULTS"""
        client = _client(tmp_path)
        client.put("/api/config/product", json={"script": {"scene": "自定义场景"}})
        resp = client.get("/api/config/product")
        data = resp.json()
        assert data["script"]["scene"] == "自定义场景"
        assert data["script"]["word_count_min"] == 150  # unchanged

    def test_delete_resets_to_defaults(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.put("/api/config/product", json={"default_name": "临时"})
        client.delete("/api/config/product")
        resp = client.get("/api/config/product")
        assert resp.json()["default_name"] == ""

    def test_delete_returns_ok(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.delete("/api/config/product")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestJobDefaultsFromProductConfig:
    """Job 创建时从 product config 读取默认 product/brand"""

    def test_job_uses_default_product(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.put(
            "/api/config/product", json={"default_name": "默认产品", "default_brand": "默认品牌"}
        )
        # 先创建项目
        client.post("/api/projects", json={"name": "test"})
        resp = client.post(
            "/api/projects/prj_001/jobs", json={"product": "", "platforms": ["douyin"]}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"] == "默认产品"
        assert data["brand"] == "默认品牌"

    def test_job_explicit_overrides_default(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.put("/api/config/product", json={"default_name": "默认产品"})
        client.post("/api/projects", json={"name": "test"})
        resp = client.post(
            "/api/projects/prj_001/jobs",
            json={"product": "特供产品", "brand": "特供品牌", "platforms": ["douyin"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"] == "特供产品"
        assert data["brand"] == "特供品牌"

    def test_batch_job_uses_default_product(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.put("/api/config/product", json={"default_name": "批处理产品"})
        client.post("/api/projects", json={"name": "test"})
        resp = client.post(
            "/api/projects/prj_001/jobs/batch",
            json={
                "product": "",
                "platforms": ["douyin"],
                "jobs": [{"name": "job1"}, {"name": "job2"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"] == "批处理产品"
        for r in data["results"]:
            assert r["product"] == "批处理产品"

    def test_batch_job_explicit_overrides_default(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.put("/api/config/product", json={"default_name": "默认"})
        client.post("/api/projects", json={"name": "test"})
        resp = client.post(
            "/api/projects/prj_001/jobs/batch",
            json={
                "product": "特供",
                "brand": "特供品牌",
                "platforms": ["douyin"],
                "jobs": [{"name": "job1"}],
            },
        )
        data = resp.json()
        assert data["product"] == "特供"
        assert data["results"][0]["brand"] == "特供品牌"

    def test_job_without_default_still_requires_product(self, tmp_path: Path) -> None:
        """default_name 为空时，仍要求显式传入 product"""
        client = _client(tmp_path)
        client.post("/api/projects", json={"name": "test"})
        resp = client.post(
            "/api/projects/prj_001/jobs",
            json={"product": "", "platforms": ["douyin"]},
        )
        assert resp.status_code == 400
