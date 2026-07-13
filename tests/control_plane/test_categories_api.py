"""Tests for GET /api/assets/categories – product-level category fallback chain."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


class TestCategoriesEndpoint:
    """GET /api/assets/categories returns configured categories."""

    def test_returns_list_of_category_items(self, tmp_path: Path) -> None:
        """Without any product config, falls back to default food categories."""
        client = _client(tmp_path)
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert "id" in item
            assert "name" in item
            assert "description" in item

    def test_default_fallback_is_food_categories(self, tmp_path: Path) -> None:
        """When no product and no asset_library config, returns 10 food categories."""
        client = _client(tmp_path)
        resp = client.get("/api/assets/categories")
        data = resp.json()
        assert len(data) == 10
        names = [c["name"] for c in data]
        assert "产地溯源" in names
        assert "成品展示" in names

    def test_product_categories_override_defaults(self, tmp_path: Path) -> None:
        """When active product has categories, they override defaults."""
        client = _client(tmp_path)
        # Create product and switch to it
        client.post("/api/products/prod_X/switch")
        # Save product-level categories
        client.put(
            "/api/products/prod_X/config",
            json={
                "categories": [
                    {"id": "origin", "name": "产地溯源", "description": "产地相关"},
                    {"id": "sorting", "name": "筛选分拣", "description": "分拣相关"},
                ],
            },
        )
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        # Should return exactly the 2 product-level categories
        assert len(data) == 2
        assert data[0]["id"] == "origin"
        assert data[0]["name"] == "产地溯源"
        assert data[0]["description"] == "产地相关"

    def test_categories_follow_active_product_switch(self, tmp_path: Path) -> None:
        """When active product changes, categories update accordingly."""
        client = _client(tmp_path)
        # Product A with its own categories
        client.post("/api/products/prod_A/switch")
        client.put(
            "/api/products/prod_A/config",
            json={
                "categories": [
                    {"id": "cat_a1", "name": "分类A1"},
                    {"id": "cat_a2", "name": "分类A2"},
                ],
            },
        )
        # Product B with different categories
        client.post("/api/products/prod_B/switch")
        client.put(
            "/api/products/prod_B/config",
            json={
                "categories": [
                    {"id": "cat_b1", "name": "分类B1"},
                    {"id": "cat_b2", "name": "分类B2"},
                    {"id": "cat_b3", "name": "分类B3"},
                ],
            },
        )

        # Switch to Product A
        client.post("/api/products/prod_A/switch")
        resp = client.get("/api/assets/categories")
        names_a = [c["name"] for c in resp.json()]
        assert "分类A1" in names_a
        assert "分类A2" in names_a

        # Switch to Product B
        client.post("/api/products/prod_B/switch")
        resp = client.get("/api/assets/categories")
        names_b = [c["name"] for c in resp.json()]
        assert "分类B1" in names_b
        assert "分类B2" in names_b
        assert "分类B3" in names_b

    def test_asset_library_categories_fallback(self, tmp_path: Path) -> None:
        """When product has no categories, falls back to asset_library.categories."""
        client = _client(tmp_path)
        client.post("/api/products/prod_no_cats/switch")
        # Product exists but has no categories — verify it returns defaults
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        # Without product or asset_library config, falls back to 10 food defaults
        assert len(data) == 10

    def test_product_with_empty_categories_returns_defaults(
        self, tmp_path: Path
    ) -> None:
        """Product with explicitly empty categories list falls back to defaults."""
        client = _client(tmp_path)
        client.post("/api/products/prod_empty/switch")
        client.put(
            "/api/products/prod_empty/config",
            json={"categories": []},
        )
        resp = client.get("/api/assets/categories")
        assert resp.status_code == 200
        data = resp.json()
        # Empty product categories -> fallback to defaults (10 food categories)
        assert len(data) == 10

    def test_endpoint_returns_valid_json_structure(self, tmp_path: Path) -> None:
        """Each category item has id, name, description fields."""
        client = _client(tmp_path)
        resp = client.get("/api/assets/categories")
        data = resp.json()
        for item in data:
            assert isinstance(item["id"], str) and item["id"] != ""
            assert isinstance(item["name"], str) and item["name"] != ""
            assert isinstance(item["description"], str)
