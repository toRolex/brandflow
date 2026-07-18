"""测试 TTS 预览接口请求头"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_preview_request_no_authorization_header(client):
    """预览请求应包含 api-key 头（通过 MiMoTTSProvider 的标准鉴权）"""
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

        assert mock_post.called, (
            f"requests.post 应被调用，但返回 status={response.status_code}"
        )
        call_kwargs = mock_post.call_args[1]
        headers = call_kwargs.get("headers", {})

        assert "api-key" in headers, "应包含 api-key 头"
