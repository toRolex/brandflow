from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


class TestProductsAPI:
    """/api/products CRUD"""

    def test_get_products_empty(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_products_after_switch(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products/prod_001/switch")
        resp = client.get("/api/products")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "prod_001"

    def test_switch_product(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post("/api/products/prod_001/switch")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_product_id"] == "prod_001"

    def test_switch_product_creates_new(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post("/api/products/new_product/switch")
        assert resp.status_code == 200
        assert resp.json()["active_product_id"] == "new_product"

        # Verify it appears in list
        list_resp = client.get("/api/products")
        ids = [p["id"] for p in list_resp.json()]
        assert "new_product" in ids

    def test_switch_and_get_config(self, tmp_path: Path) -> None:
        """切换产品后应能获取该产品配置"""
        client = _client(tmp_path)
        client.post("/api/products/prod_001/switch")
        resp = client.get("/api/products/prod_001/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "prod_001"
        assert "default_name" in data
        assert "default_brand" in data
        assert "script" in data

    def test_put_product_config(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products/prod_001/switch")
        resp = client.put(
            "/api/products/prod_001/config",
            json={"default_name": "羊肚菌", "default_brand": "菌王"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_name"] == "羊肚菌"
        assert data["default_brand"] == "菌王"

    def test_put_product_config_deep_merge(self, tmp_path: Path) -> None:
        """PUT 只更新传入字段，其他保留 DEFAULTS"""
        client = _client(tmp_path)
        client.post("/api/products/prod_001/switch")
        client.put(
            "/api/products/prod_001/config",
            json={"script": {"scene": "自定义场景"}},
        )
        resp = client.get("/api/products/prod_001/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["script"]["scene"] == "自定义场景"
        assert data["script"]["word_count_min"] == 150  # unchanged

    def test_get_config_nonexistent_product(self, tmp_path: Path) -> None:
        """不存在的产品返回 404"""
        client = _client(tmp_path)
        resp = client.get("/api/products/nonexistent/config")
        assert resp.status_code == 404

    def test_put_config_nonexistent_product(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.put(
            "/api/products/nonexistent/config",
            json={"default_name": "test"},
        )
        assert resp.status_code == 404

    def test_multiple_products_independent_configs(self, tmp_path: Path) -> None:
        """多个产品的配置应独立存储"""
        client = _client(tmp_path)
        # Create two products with different configs
        client.post("/api/products/prod_001/switch")
        client.put(
            "/api/products/prod_001/config",
            json={"default_name": "羊肚菌"},
        )

        client.post("/api/products/prod_002/switch")
        client.put(
            "/api/products/prod_002/config",
            json={"default_name": "竹荪"},
        )

        # Verify each product has its own config
        resp1 = client.get("/api/products/prod_001/config")
        assert resp1.json()["default_name"] == "羊肚菌"

        resp2 = client.get("/api/products/prod_002/config")
        assert resp2.json()["default_name"] == "竹荪"

    def test_switch_active_product(self, tmp_path: Path) -> None:
        """切换后 GET /api/config/product 应返回新产品配置"""
        client = _client(tmp_path)
        client.post("/api/products/prod_001/switch")
        client.put(
            "/api/products/prod_001/config",
            json={"default_name": "羊肚菌"},
        )

        client.post("/api/products/prod_002/switch")
        client.put(
            "/api/products/prod_002/config",
            json={"default_name": "竹荪"},
        )

        # Switch back to prod_001 and check active config
        client.post("/api/products/prod_001/switch")
        resp = client.get("/api/config/product")
        assert resp.status_code == 200
        assert resp.json()["default_name"] == "羊肚菌"

    def test_list_two_products(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products/a/switch")
        client.post("/api/products/b/switch")
        resp = client.get("/api/products")
        data = resp.json()
        assert len(data) == 2
        ids = [p["id"] for p in data]
        assert "a" in ids
        assert "b" in ids
