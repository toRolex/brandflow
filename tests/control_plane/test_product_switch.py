from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


class TestProductSwitch:
    """POST /api/products/{id}/switch 切换活跃产品。"""

    def test_switch_creates_product(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post("/api/products/prod_a/switch")
        assert resp.status_code == 200
        assert resp.json()["active_product_id"] == "prod_a"

    def test_switch_changes_active_product(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products/prod_a/switch")
        client.put("/api/products/prod_a/config", json={"default_name": "产品 A"})

        client.post("/api/products/prod_b/switch")
        client.put("/api/products/prod_b/config", json={"default_name": "产品 B"})

        # 切换回 A 后，/api/config/product 应返回 A 的配置
        client.post("/api/products/prod_a/switch")
        resp = client.get("/api/config/product")
        assert resp.status_code == 200
        assert resp.json()["default_name"] == "产品 A"

    def test_switch_does_not_mutate_other_product_config(self, tmp_path: Path) -> None:
        """切换活跃产品时，其他产品的配置保持不变。"""
        client = _client(tmp_path)
        client.post("/api/products/prod_a/switch")
        client.put("/api/products/prod_a/config", json={"default_name": "产品 A"})

        client.post("/api/products/prod_b/switch")
        client.put("/api/products/prod_b/config", json={"default_name": "产品 B"})

        resp = client.get("/api/products/prod_a/config")
        assert resp.status_code == 200
        assert resp.json()["default_name"] == "产品 A"

    def test_switch_is_reflected_in_products_list(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/products/prod_a/switch")
        client.post("/api/products/prod_b/switch")

        resp = client.get("/api/products")
        data = resp.json()
        assert len(data) == 2
        ids = {p["id"] for p in data}
        assert ids == {"prod_a", "prod_b"}

    def test_job_uses_active_product_config_after_switch(self, tmp_path: Path) -> None:
        """切换产品后，创建 Job 时使用新的活跃产品配置作为默认值。"""
        client = _client(tmp_path)
        client.post("/api/products/prod_a/switch")
        client.put("/api/products/prod_a/config", json={"default_name": "产品 A", "default_brand": "品牌 A"})

        client.post("/api/products/prod_b/switch")
        client.put("/api/products/prod_b/config", json={"default_name": "产品 B", "default_brand": "品牌 B"})

        client.post("/api/projects", json={"name": "test"})
        resp = client.post(
            "/api/projects/prj_001/jobs",
            json={"product": "", "platforms": ["douyin"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["product"] == "产品 B"
        assert data["brand"] == "品牌 B"

    def test_put_product_config_does_not_change_active_product(self, tmp_path: Path) -> None:
        """更新非活跃产品配置时，活跃产品应保持不变。"""
        client = _client(tmp_path)
        client.post("/api/products/prod_a/switch")
        client.put("/api/products/prod_a/config", json={"default_name": "产品 A"})

        client.post("/api/products/prod_b/switch")
        client.put("/api/products/prod_b/config", json={"default_name": "产品 B"})

        # 当前活跃是 prod_b；直接修改 prod_a 的配置
        resp = client.put("/api/products/prod_a/config", json={"default_name": "产品 A 已修改"})
        assert resp.status_code == 200

        # 活跃产品仍应为 prod_b
        active_resp = client.get("/api/config/product")
        assert active_resp.json()["default_name"] == "产品 B"

        # prod_a 的配置确实被修改
        a_resp = client.get("/api/products/prod_a/config")
        assert a_resp.json()["default_name"] == "产品 A 已修改"

    def test_edit_non_active_config_does_not_switch_active_for_jobs(self, tmp_path: Path) -> None:
        """编辑非活跃产品配置后，创建 Job 仍使用活跃产品的默认值。"""
        client = _client(tmp_path)
        # 设置 prod_a 为活跃产品并配置
        client.post("/api/products/prod_a/switch")
        client.put("/api/products/prod_a/config", json={"default_name": "产品 A", "default_brand": "品牌 A"})

        # 切换到 prod_b 并配置
        client.post("/api/products/prod_b/switch")
        client.put("/api/products/prod_b/config", json={"default_name": "产品 B", "default_brand": "品牌 B"})

        # 当前活跃是 prod_b；编辑 prod_a 的配置（不切换）
        resp = client.put("/api/products/prod_a/config", json={"default_name": "产品 A 已修改"})
        assert resp.status_code == 200

        # 创建 Job 应使用活跃产品 prod_b 的默认值
        client.post("/api/projects", json={"name": "test"})
        job_resp = client.post(
            "/api/projects/prj_001/jobs",
            json={"product": "", "platforms": ["douyin"]},
        )
        assert job_resp.status_code == 200
        job_data = job_resp.json()
        assert job_data["product"] == "产品 B"
        assert job_data["brand"] == "品牌 B"
