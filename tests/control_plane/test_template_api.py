from __future__ import annotations

import json
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
        names = {item["name"] for item in data}
        assert names == {"通用带货脚本", "第二个模板"}


class TestScriptTemplateJobIntegration:
    """模板 + Job 创建端到端"""

    TEMPLATE_PAYLOAD = {
        "name": "带货模板",
        "description": "描述",
        "slots": [
            {"type": "hook", "label": "开头钩子", "required": True, "max_length": 60, "hint": ""},
            {"type": "selling_point", "label": "核心卖点", "required": True, "max_length": 200, "hint": ""},
        ],
        "variables": [
            {"name": "product_name", "label": "产品名", "source": "product_config"},
            {"name": "discount", "label": "优惠信息", "source": "manual"},
        ],
        "default_config_override": {},
    }

    def test_create_job_from_template(self, tmp_path: Path) -> None:
        """选择模板、填充变量、渲染脚本后创建 Import 模式 Job。"""
        client = _client(tmp_path)

        # 1. 创建模板
        create_resp = client.post("/api/config/templates", json=self.TEMPLATE_PAYLOAD)
        assert create_resp.status_code == 200
        tmpl_id = create_resp.json()["id"]

        # 2. 渲染 preview
        preview_resp = client.post(
            f"/api/config/templates/{tmpl_id}/preview",
            json={
                "slot_contents": {
                    "开头钩子": "今天给大家推荐{product_name}！",
                    "核心卖点": "{product_name}限时{discount}，手慢无。",
                },
                "variable_values": {
                    "product_name": "羊肚菌",
                    "discount": "买一送一",
                },
            },
        )
        assert preview_resp.status_code == 200
        rendered = preview_resp.json()["rendered_script"]
        assert "羊肚菌" in rendered
        assert "买一送一" in rendered
        assert "{product_name}" not in rendered

        # 3. 创建项目
        project_resp = client.post("/api/projects", json={"name": "模板测试项目"})
        assert project_resp.status_code == 200
        project_id = project_resp.json()["id"]

        # 4. 使用渲染后的 manual_script 创建 Import 模式 Job
        job_resp = client.post(
            f"/api/projects/{project_id}/jobs",
            json={
                "product": "羊肚菌",
                "brand": "菌王山珍",
                "platforms": ["douyin"],
                "mode": "import",
                "manual_script": rendered,
                "skip_subtitle": True,
            },
        )
        assert job_resp.status_code == 200
        job = job_resp.json()
        assert job["mode"] == "import"
        assert job["manual_script"] == rendered
        assert job["product"] == "羊肚菌"
        assert job["brand"] == "菌王山珍"

        # 5. 磁盘持久化验证
        job_path = (
            tmp_path
            / "workspace"
            / "projects"
            / project_id
            / "control"
            / "jobs"
            / f"{job['job_id']}.json"
        )
        raw = json.loads(job_path.read_text(encoding="utf-8"))
        assert raw["mode"] == "import"
        assert raw["manual_script"] == rendered


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
