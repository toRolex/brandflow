"""黑盒测试：只关心输入输出，不关心内部实现"""

import pytest
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


class TestTTSConfigBlackBox:
    def test_get_config_returns_valid_json(self, client):
        response = client.get("/api/tts/config")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "model" in data
        assert "voice" in data

    def test_save_config_with_all_fields(self, client):
        config = {
            "model": "mimo-v2.5-tts-voicedesign",
            "voice": "CustomVoice",
            "fallback_voice": "BackupVoice",
            "randomize_voice": False,
            "random_voices": ["A", "B"],
            "voice_design_prompt": "年轻女性",
            "style_prompt": "活泼热情",
            "audio_format": "wav",
            "sample_rate": 44100,
            "bitrate": 192000,
            "channel": 2,
        }
        response = client.put("/api/tts/config", json=config)
        assert response.status_code == 200
        assert response.json()["success"] is True

        loaded = client.get("/api/tts/config").json()
        for key, value in config.items():
            assert loaded[key] == value

    def test_save_config_with_partial_fields(self, client):
        response = client.put("/api/tts/config", json={"model": "custom-model"})
        assert response.status_code == 200

        loaded = client.get("/api/tts/config").json()
        assert loaded["model"] == "custom-model"

    def test_get_voices_returns_list(self, client):
        response = client.get("/api/tts/voices")
        assert response.status_code == 200
        data = response.json()
        assert "preset_voices" in data
        assert isinstance(data["preset_voices"], list)
        assert len(data["preset_voices"]) > 0
        for voice in data["preset_voices"]:
            assert "id" in voice
            assert "label" in voice
            assert "note" in voice


class TestTTSPreviewBlackBox:
    def test_preview_without_api_key_returns_error(self, client, monkeypatch):
        monkeypatch.delenv("MIMO_API_KEY", raising=False)
        monkeypatch.delenv("TTS_API_KEY", raising=False)
        response = client.post(
            "/api/tts/preview", json={"text": "测试文本", "model": "mimo-v2.5-tts"}
        )
        assert response.status_code == 500
        assert "MIMO_API_KEY" in response.json()["detail"]

    def test_preview_with_invalid_model_returns_error(self, client, monkeypatch):
        monkeypatch.delenv("MIMO_API_KEY", raising=False)
        monkeypatch.delenv("TTS_API_KEY", raising=False)
        response = client.post(
            "/api/tts/preview", json={"text": "测试文本", "model": ""}
        )
        assert response.status_code in [400, 422, 500]
