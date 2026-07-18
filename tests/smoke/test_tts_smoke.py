"""冒烟测试：验证TTS核心功能基本可用"""

import pytest
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestTTSSmoke:
    def test_tts_config_api_accessible(self, client):
        response = client.get("/api/tts/config")
        assert response.status_code == 200

    def test_tts_voices_api_accessible(self, client):
        response = client.get("/api/tts/voices")
        assert response.status_code == 200
        assert "preset_voices" in response.json()

    def test_tts_config_save_and_load(self, client):
        save_response = client.put(
            "/api/tts/config", json={"model": "mimo-v2.5-tts", "voice": "Mia"}
        )
        assert save_response.status_code == 200
        assert save_response.json()["success"] is True

        load_response = client.get("/api/tts/config")
        assert load_response.status_code == 200
        assert load_response.json()["model"] == "mimo-v2.5-tts"

    def test_tts_preview_requires_text(self, client):
        response = client.post("/api/tts/preview", json={})
        assert response.status_code == 422
