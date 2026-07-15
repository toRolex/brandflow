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
            "style_prompt": "活泼热情",
        }
        response = client.put("/api/tts/config", json=config)
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_get_voices_default(self, client):
        response = client.get("/api/tts/voices")
        assert response.status_code == 200
        data = response.json()
        assert "preset_voices" in data
        assert len(data["preset_voices"]) > 0

    def test_get_voices_with_model_mimo(self, client):
        response = client.get("/api/tts/voices?model=mimo-v2.5-tts")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        assert len(voices) > 0
        assert all(v["model"] == "mimo-v2.5-tts" for v in voices)

    def test_get_voices_with_model_qwen_instruct(self, client):
        """model=qwen3-tts-instruct-flash 应排除 INSTRUCT_UNSUPPORTED_VOICES"""
        response = client.get("/api/tts/voices?model=qwen3-tts-instruct-flash")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        ids = {v["id"] for v in voices}
        assert "Jennifer" not in ids
        assert "Ryan" not in ids
        assert "Katerina" not in ids
        assert "Rocky" in ids  # a supported voice is still there

    def test_get_voices_with_model_qwen_flash(self, client):
        """model=qwen3-tts-flash 应返回完整音色列表（含 3 个不支持 instruct 的音色）"""
        response = client.get("/api/tts/voices?model=qwen3-tts-flash")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        ids = {v["id"] for v in voices}
        assert "Jennifer" in ids
        assert "Ryan" in ids
        assert "Katerina" in ids

    def test_get_voices_unknown_model_returns_400(self, client):
        response = client.get("/api/tts/voices?model=unknown-model")
        assert response.status_code == 400

    def test_get_voices_with_provider_mimo(self, client):
        """backward compat: ?provider=mimo 仍有效"""
        response = client.get("/api/tts/voices?provider=mimo")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        assert all(v["model"] == "mimo-v2.5-tts" for v in voices)

    def test_get_voices_with_provider_qwen(self, client):
        """backward compat: ?provider=qwen 仍有效"""
        response = client.get("/api/tts/voices?provider=qwen")
        assert response.status_code == 200
        voices = response.json()["preset_voices"]
        assert all(v["model"].startswith("qwen") for v in voices)

    def test_get_voices_unknown_provider_returns_400(self, client):
        """backward compat: 未知 provider 仍返回 400"""
        response = client.get("/api/tts/voices?provider=unknown")
        assert response.status_code == 400


class TestTTSPreviewAPI:
    def test_preview_requires_text(self, client):
        response = client.post("/api/tts/preview", json={})
        assert response.status_code == 422

    def test_preview_with_valid_text(self, client):
        response = client.post(
            "/api/tts/preview",
            json={
                "text": "测试文本",
                "model": "mimo-v2.5-tts",
                "voice": "Mia",
                "style_prompt": "自然",
            },
        )
        assert response.status_code in [200, 500]
