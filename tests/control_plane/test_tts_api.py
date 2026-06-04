import pytest
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestTTSConfigAPI:
    def test_get_config_default(self, client):
        response = client.get("/api/tts/config")
        assert response.status_code == 200
        data = response.json()
        assert "model" in data
        assert "voice" in data

    def test_save_config(self, client):
        config = {
            "model": "mimo-v2.5-tts-voicedesign",
            "voice_design_prompt": "年轻女性，声音甜美",
            "style_prompt": "活泼热情"
        }
        response = client.put("/api/tts/config", json=config)
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_get_voices(self, client):
        response = client.get("/api/tts/voices")
        assert response.status_code == 200
        data = response.json()
        assert "preset_voices" in data
        assert len(data["preset_voices"]) > 0


class TestTTSMonitorAPI:
    def test_get_metrics(self, client):
        response = client.get("/api/tts/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "success_rate" in data
        assert "avg_latency_ms" in data

    def test_get_logs(self, client):
        response = client.get("/api/tts/logs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_error_distribution(self, client):
        response = client.get("/api/tts/errors/distribution")
        assert response.status_code == 200
        data = response.json()
        assert "distribution" in data


class TestTTSPreviewAPI:
    def test_preview_requires_text(self, client):
        response = client.post("/api/tts/preview", json={})
        assert response.status_code == 422

    def test_preview_without_api_key(self, client):
        response = client.post("/api/tts/preview", json={
            "text": "测试文本",
            "model": "mimo-v2.5-tts",
            "voice": "Mia",
            "style_prompt": "自然"
        })
        assert response.status_code == 500
