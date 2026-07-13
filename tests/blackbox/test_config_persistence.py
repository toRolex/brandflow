"""测试前端配置修改是否持久化到配置文件"""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_config():
    config_file = Path("config/app_config.json")
    original = None
    if config_file.exists():
        original = config_file.read_text(encoding="utf-8")
    yield
    if original:
        config_file.write_text(original, encoding="utf-8")


class TestConfigPersistence:
    def test_save_tts_config_persists_to_file(self, client):
        config = {
            "model": "test-persist-model",
            "voice": "test-persist-voice",
            "style_prompt": "test-persist-style",
        }
        response = client.put("/api/tts/config", json=config)
        assert response.status_code == 200
        assert response.json()["success"] is True

        config_file = Path("config/app_config.json")
        assert config_file.exists()

        with open(config_file, encoding="utf-8") as f:
            saved_data = json.load(f)

        # set_tts() 优先写入活跃产品的 product-level tts
        active_id = saved_data.get("active_product_id", "")
        if active_id:
            product = next(
                (p for p in saved_data.get("products", []) if p.get("id") == active_id),
                None,
            )
            tts = (
                product["tts"]
                if product and "tts" in product
                else saved_data.get("tts", {})
            )
        else:
            tts = saved_data.get("tts", {})
        assert tts["model"] == "test-persist-model"
        assert tts["voice"] == "test-persist-voice"
        assert tts["style_prompt"] == "test-persist-style"

    def test_config_persists_across_requests(self, client):
        client.put("/api/tts/config", json={"model": "persisted-model"})

        response = client.get("/api/tts/config")
        assert response.status_code == 200
        assert response.json()["model"] == "persisted-model"

    def test_partial_update_preserves_other_fields(self, client):
        client.put(
            "/api/tts/config",
            json={
                "model": "original-model",
                "voice": "original-voice",
                "style_prompt": "original-style",
            },
        )

        client.put("/api/tts/config", json={"model": "updated-model"})

        response = client.get("/api/tts/config")
        data = response.json()
        assert data["model"] == "updated-model"
        assert data["voice"] == "original-voice"
        assert data["style_prompt"] == "original-style"

    def test_nested_config_persists(self, client):
        config = {
            "director_character": "年轻女性",
            "director_scene": "厨房",
            "director_guidance": "热情洋溢",
        }
        client.put("/api/tts/config", json=config)

        config_file = Path("config/app_config.json")
        with open(config_file, encoding="utf-8") as f:
            saved_data = json.load(f)

        active_id = saved_data.get("active_product_id", "")
        if active_id:
            product = next(
                (p for p in saved_data.get("products", []) if p.get("id") == active_id),
                None,
            )
            tts = (
                product["tts"]
                if product and "tts" in product
                else saved_data.get("tts", {})
            )
        else:
            tts = saved_data.get("tts", {})
        assert "director" in tts
        assert tts["director"]["character"] == "年轻女性"
        assert tts["director"]["scene"] == "厨房"
        assert tts["director"]["guidance"] == "热情洋溢"

    def test_audio_tags_config_persists(self, client):
        config = {
            "audio_tags_enabled": True,
            "audio_tags": "(温柔)[笑声]",
        }
        client.put("/api/tts/config", json=config)

        config_file = Path("config/app_config.json")
        with open(config_file, encoding="utf-8") as f:
            saved_data = json.load(f)

        active_id = saved_data.get("active_product_id", "")
        if active_id:
            product = next(
                (p for p in saved_data.get("products", []) if p.get("id") == active_id),
                None,
            )
            tts = (
                product["tts"]
                if product and "tts" in product
                else saved_data.get("tts", {})
            )
        else:
            tts = saved_data.get("tts", {})
        assert "audio_tags" in tts
        assert tts["audio_tags"]["enabled"] is True
        assert tts["audio_tags"]["tags"] == "(温柔)[笑声]"

    def test_config_survives_new_client(self):
        app1 = create_app()
        client1 = TestClient(app1)
        client1.put("/api/tts/config", json={"model": "survived-model"})

        app2 = create_app()
        client2 = TestClient(app2)

        response = client2.get("/api/tts/config")
        assert response.status_code == 200
        assert response.json()["model"] == "survived-model"

    def test_multiple_config_sections_independent(self, client):
        client.put("/api/tts/config", json={"model": "tts-model"})

        config_file = Path("config/app_config.json")
        with open(config_file, encoding="utf-8") as f:
            saved_data = json.load(f)

        active_id = saved_data.get("active_product_id", "")
        if active_id:
            product = next(
                (p for p in saved_data.get("products", []) if p.get("id") == active_id),
                None,
            )
            tts = (
                product["tts"]
                if product and "tts" in product
                else saved_data.get("tts", {})
            )
        else:
            tts = saved_data.get("tts", {})
        assert tts["model"] == "tts-model"
        assert "products" in saved_data
