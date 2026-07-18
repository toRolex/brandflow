"""测试 TTS 预览响应格式"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_preview_response_wav_content_type(client):
    """当 audio_format=wav 时，响应应为 audio/wav"""
    with (
        patch("requests.post") as mock_post,
        patch("apps.control_plane.routes.tts.app_config") as mock_config,
    ):
        mock_config.get_api_key.return_value = "test-api-key"
        mock_config.get_api_base_url.return_value = "https://api.xiaomimimo.com/v1"
        mock_config.get_tts_config.return_value = {"provider": "mimo"}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"audio": {"data": "dGVzdA=="}}}]
        }
        mock_post.return_value = mock_response

        response = client.post(
            "/api/tts/preview",
            json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert "preview.wav" in response.headers.get("content-disposition", "")
