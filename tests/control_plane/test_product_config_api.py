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

    def test_delete_keeps_product_entity(self, tmp_path: Path) -> None:
        """重置后产品实体仍保留在产品列表中"""
        client = _client(tmp_path)
        client.put("/api/config/product", json={"default_name": "临时"})
        client.delete("/api/config/product")
        products = client.get("/api/products").json()
        assert len(products) == 1
        assert products[0]["id"] == "default"

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
            "/api/config/product",
            json={"default_name": "默认产品", "default_brand": "默认品牌"},
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


# ── S3/S4: product-level category CRUD via /api/products/{product_id}/config ──


class TestProductConfigCategoriesAPI:
    """产品级分类的 API CRUD 和 fallback 行为"""

    def test_get_product_config_includes_categories(self, tmp_path: Path) -> None:
        """GET /api/products/{id}/config 返回产品级 categories"""
        client = _client(tmp_path)
        # 先创建产品
        client.post("/api/products/prod_A/switch")
        # 写入分类
        client.put(
            "/api/products/prod_A/config",
            json={
                "categories": [
                    {"id": "origin", "name": "产地溯源", "description": "原产地"},
                    {"id": "sorting", "name": "筛选分拣", "description": "分拣"},
                ],
            },
        )
        resp = client.get("/api/products/prod_A/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "categories" in data
        assert len(data["categories"]) == 2
        assert data["categories"][0]["id"] == "origin"
        assert data["categories"][0]["name"] == "产地溯源"
        assert data["categories"][0]["description"] == "原产地"
        assert data["categories"][1]["id"] == "sorting"
        assert data["categories"][1]["name"] == "筛选分拣"

    def test_put_product_config_saves_categories(self, tmp_path: Path) -> None:
        """PUT /api/products/{id}/config 保存 categories 后独立读取一致"""
        client = _client(tmp_path)
        client.post("/api/products/prod_B/switch")
        client.put(
            "/api/products/prod_B/config",
            json={
                "categories": [
                    {"id": "tasting", "name": "试吃品尝", "description": "试吃"},
                ],
            },
        )
        # 独立读取验证
        resp = client.get("/api/products/prod_B/config")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["categories"]) == 1
        assert data["categories"][0]["id"] == "tasting"

    def test_product_no_categories_returns_defaults(self, tmp_path: Path) -> None:
        """产品未配置 categories 时 GET 返回 DEFAULTS 空列表"""
        client = _client(tmp_path)
        client.post("/api/products/prod_C/switch")
        resp = client.get("/api/products/prod_C/config")
        assert resp.status_code == 200
        data = resp.json()
        # DEFAULTS 的 product.categories 为空列表
        assert data["categories"] == []

    def test_product_empty_categories_returns_empty_list(self, tmp_path: Path) -> None:
        """产品显式设置空 categories 列表"""
        client = _client(tmp_path)
        client.post("/api/products/prod_D/switch")
        client.put(
            "/api/products/prod_D/config",
            json={"categories": []},
        )
        resp = client.get("/api/products/prod_D/config")
        assert resp.status_code == 200
        assert resp.json()["categories"] == []

    def test_categories_without_id_field_preserved(self, tmp_path: Path) -> None:
        """categories 中的 id/name/description 字段完整保留"""
        client = _client(tmp_path)
        client.post("/api/products/prod_E/switch")
        client.put(
            "/api/products/prod_E/config",
            json={
                "categories": [
                    {
                        "id": "a",
                        "name": "分类A",
                        "description": "描述A",
                        "vision_prompt": "vpA",
                    },
                    {"id": "b", "name": "分类B", "description": "描述B"},
                ],
            },
        )
        resp = client.get("/api/products/prod_E/config")
        data = resp.json()
        assert data["categories"][0]["vision_prompt"] == "vpA"
        assert "vision_prompt" not in data["categories"][1]
