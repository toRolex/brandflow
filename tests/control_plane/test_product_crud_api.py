from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


class TestCreateProductAPI:
    """POST /api/products 新建产品。"""

    def test_create_product_returns_id_and_name(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post("/api/products", json={"name": "羊肚菌"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "羊肚菌"
        assert data["name"] == "羊肚菌"

    def test_create_product_appears_in_list(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "羊肚菌"})
        resp = client.get("/api/products")
        ids = [p["id"] for p in resp.json()]
        assert "羊肚菌" in ids

    def test_create_product_empty_name_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post("/api/products", json={"name": ""})
        assert resp.status_code == 400

    def test_create_product_whitespace_name_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post("/api/products", json={"name": "   "})
        assert resp.status_code == 400


class TestRenameProductAPI:
    """PATCH /api/products/{product_id} 重命名产品。"""

    def test_rename_product_returns_id_and_name(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "羊肚菌"})
        resp = client.patch("/api/products/羊肚菌", json={"name": "新鲜羊肚菌"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "羊肚菌"
        assert data["name"] == "新鲜羊肚菌"

    def test_rename_persists_in_product_list(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "羊肚菌"})
        client.patch("/api/products/羊肚菌", json={"name": "新鲜羊肚菌"})
        resp = client.get("/api/products")
        names = [p["name"] for p in resp.json()]
        assert "新鲜羊肚菌" in names

    def test_rename_nonexistent_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.patch("/api/products/nonexistent", json={"name": "新名称"})
        assert resp.status_code == 404

    def test_rename_empty_name_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "羊肚菌"})
        resp = client.patch("/api/products/羊肚菌", json={"name": ""})
        assert resp.status_code == 400

    def test_rename_whitespace_name_returns_400(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "羊肚菌"})
        resp = client.patch("/api/products/羊肚菌", json={"name": "   "})
        assert resp.status_code == 400


class TestDeleteProductAPI:
    """DELETE /api/products/{product_id} 删除产品。"""

    def test_delete_product_returns_status(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "羊肚菌"})
        resp = client.delete("/api/products/羊肚菌")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert "active_product_id" in data

    def test_delete_product_removes_from_list(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "羊肚菌"})
        client.delete("/api/products/羊肚菌")
        resp = client.get("/api/products")
        ids = [p["id"] for p in resp.json()]
        assert "羊肚菌" not in ids

    def test_delete_nonexistent_returns_404(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.delete("/api/products/nonexistent")
        assert resp.status_code == 404

    def test_delete_active_product_resets_active_to_first_remaining(
        self, tmp_path: Path
    ) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "产品A"})
        client.post("/api/products", json={"name": "产品B"})
        client.post("/api/products", json={"name": "产品C"})
        # 确保 产品B 是活跃产品
        client.post("/api/products/产品B/switch")

        resp = client.delete("/api/products/产品B")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        # 活跃产品应重置为剩余产品之一
        assert data["active_product_id"] != "产品B"
        assert data["active_product_id"] != ""

    def test_delete_last_product_clears_active(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "唯一产品"})

        resp = client.delete("/api/products/唯一产品")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["active_product_id"] == ""

    def test_delete_non_active_product_does_not_change_active(
        self, tmp_path: Path
    ) -> None:
        client = _client(tmp_path)
        client.post("/api/products", json={"name": "产品A"})
        client.post("/api/products", json={"name": "产品B"})
        client.post("/api/products/产品A/switch")

        resp = client.delete("/api/products/产品B")
        assert resp.status_code == 200
        assert resp.json()["active_product_id"] == "产品A"
