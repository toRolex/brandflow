from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


class TestScriptTemplateAPI:
    """/api/config/templates CRUD"""

    TEMPLATE_PAYLOAD = {
        "name": "通用带货脚本",
        "description": "适用于食品类短视频带货",
        "slots": [
            {"type": "hook", "label": "开头钩子", "required": True, "max_length": 60, "hint": "吸引眼球的开头"},
            {"type": "selling_point", "label": "核心卖点", "required": True, "max_length": 200, "hint": "产品核心卖点"},
        ],
        "variables": [
            {"name": "product_name", "label": "产品名", "source": "product_config"},
            {"name": "brand_name", "label": "品牌名", "source": "product_config"},
        ],
        "default_config_override": {"word_count_max": 200},
    }

    def test_list_empty(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/api/config/templates")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_template(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post("/api/config/templates", json=self.TEMPLATE_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "通用带货脚本"
        assert data["id"].startswith("tmpl_")
        assert len(data["slots"]) == 2
        assert len(data["variables"]) == 2

    def test_get_template(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        create_resp = client.post("/api/config/templates", json=self.TEMPLATE_PAYLOAD)
        tmpl_id = create_resp.json()["id"]

        resp = client.get(f"/api/config/templates/{tmpl_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "通用带货脚本"

    def test_get_template_not_found(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/api/config/templates/non_existent")
        assert resp.status_code == 404

    def test_update_template(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        create_resp = client.post("/api/config/templates", json=self.TEMPLATE_PAYLOAD)
        tmpl_id = create_resp.json()["id"]

        update_payload = {
            "id": tmpl_id,
            "name": "更新后的模板",
            "description": "新的描述",
            "slots": [],
            "variables": [],
            "default_config_override": {},
        }
        resp = client.put(f"/api/config/templates/{tmpl_id}", json=update_payload)
        assert resp.status_code == 200
        assert resp.json()["name"] == "更新后的模板"

    def test_update_template_not_found(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.put(
            "/api/config/templates/non_existent",
            json=self.TEMPLATE_PAYLOAD,
        )
        assert resp.status_code == 404

    def test_delete_template(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        create_resp = client.post("/api/config/templates", json=self.TEMPLATE_PAYLOAD)
        tmpl_id = create_resp.json()["id"]

        resp = client.delete(f"/api/config/templates/{tmpl_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # 确认已删除
        get_resp = client.get(f"/api/config/templates/{tmpl_id}")
        assert get_resp.status_code == 404

    def test_delete_template_not_found(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.delete("/api/config/templates/non_existent")
        assert resp.status_code == 404

    def test_list_after_create(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        client.post("/api/config/templates", json=self.TEMPLATE_PAYLOAD)
        client.post("/api/config/templates", json={
            "name": "第二个模板",
            "description": "描述",
            "slots": [],
            "variables": [],
            "default_config_override": {},
        })
        resp = client.get("/api/config/templates")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "通用带货脚本"
        assert data[1]["name"] == "第二个模板"


class TestScriptTemplatePreview:
    """POST /api/config/templates/{id}/preview"""

    TEMPLATE_PAYLOAD = {
        "name": "带货模板",
        "description": "描述",
        "slots": [
            {"type": "hook", "label": "开头钩子", "required": True, "max_length": 60, "hint": ""},
            {"type": "selling_point", "label": "核心卖点", "required": True, "max_length": 200, "hint": ""},
        ],
        "variables": [
            {"name": "product_name", "label": "产品名", "source": "product_config"},
        ],
        "default_config_override": {},
    }

    def test_preview_renders_script(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        create_resp = client.post("/api/config/templates", json=self.TEMPLATE_PAYLOAD)
        tmpl_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/config/templates/{tmpl_id}/preview",
            json={
                "slot_contents": {
                    "开头钩子": "你知道吗？这是一款好产品",
                    "核心卖点": "产品名称为{product_name}，品质上乘",
                },
                "variable_values": {"product_name": "羊肚菌"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "rendered_script" in data
        assert "羊肚菌" in data["rendered_script"]
        assert "{product_name}" not in data["rendered_script"]

    def test_preview_not_found(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post(
            "/api/config/templates/non_existent/preview",
            json={"slot_contents": {}, "variable_values": {}},
        )
        assert resp.status_code == 404

    def test_preview_empty_template(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        create_resp = client.post("/api/config/templates", json={
            "name": "空模板", "description": "", "slots": [], "variables": [],
            "default_config_override": {},
        })
        tmpl_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/config/templates/{tmpl_id}/preview",
            json={"slot_contents": {}, "variable_values": {}},
        )
        assert resp.status_code == 200
        assert resp.json()["rendered_script"] == ""
