"""测试 TTS 预览响应格式"""

import base64
import io
import wave
from collections.abc import Callable
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from apps.control_plane.app import create_app
from packages.provider_config.tts_config import TTSConfig


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_preview_response_wav_content_type(client, wav_bytes: Callable[..., bytes]):
    """当 audio_format=wav 时，响应应为 audio/wav"""
    source_audio = wav_bytes()
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
            "choices": [
                {
                    "message": {
                        "audio": {
                            "data": base64.b64encode(source_audio).decode("ascii")
                        }
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        response = client.post(
            "/api/tts/preview",
            json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/wav"
        assert "preview.wav" in response.headers.get("content-disposition", "")
        assert response.content == source_audio
        with wave.open(io.BytesIO(response.content), "rb") as wav_file:
            assert wav_file.getnframes() / wav_file.getframerate() > 0


def test_preview_rejects_non_wav_payload_without_leaking_provider_data(client):
    provider_secret = "secret-provider-response"
    with (
        patch("requests.post") as mock_post,
        patch("apps.control_plane.routes.tts.app_config") as mock_config,
    ):
        mock_config.get_api_key.return_value = "secret-api-key"
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            "audio": base64.b64encode(provider_secret.encode()).decode("ascii")
        }
        mock_post.return_value = mock_response

        response = client.post(
            "/api/tts/preview",
            json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
        )

        assert response.status_code == 502
        assert response.json()["detail"] == "TTS returned invalid WAV audio"
        assert provider_secret not in response.text
        assert "secret-api-key" not in response.text


@pytest.mark.parametrize(
    "malformation",
    ["header-only", "zero-frame", "zero-framerate", "truncated-frame-data"],
)
def test_preview_rejects_malformed_wav_container(
    client,
    wav_bytes: Callable[..., bytes],
    malformation: str,
):
    if malformation == "header-only":
        source_audio = b"RIFF\x04\x00\x00\x00WAVE"
    elif malformation == "zero-frame":
        source_audio = wav_bytes(0)
    elif malformation == "zero-framerate":
        malformed_audio = bytearray(wav_bytes(1))
        malformed_audio[24:32] = b"\x00" * 8
        source_audio = bytes(malformed_audio)
    else:
        source_audio = wav_bytes()[:-2]
    with (
        patch("requests.post") as mock_post,
        patch("apps.control_plane.routes.tts.app_config") as mock_config,
    ):
        mock_config.get_api_key.return_value = "test-api-key"
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            "audio": base64.b64encode(source_audio).decode("ascii")
        }
        mock_post.return_value = mock_response

        response = client.post(
            "/api/tts/preview",
            json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
        )

        assert response.status_code == 502
        assert response.json()["detail"] == "TTS returned invalid WAV audio"


def test_preview_preserves_raw_pcm16_payload(client):
    source_audio = b"\x00\x00\x01\x00\xff\x7f"
    config = TTSConfig(
        model="mimo-v2.5-tts",
        voice="Mia",
        audio_format="pcm16",
    ).with_defaults()
    with (
        patch("requests.post") as mock_post,
        patch("apps.control_plane.routes.tts.app_config") as mock_config,
        patch("apps.control_plane.routes.tts.config_manager") as mock_manager,
    ):
        mock_config.get_api_key.return_value = "test-api-key"
        mock_manager.get_config.return_value.with_defaults.return_value = config
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {
            "audio": base64.b64encode(source_audio).decode("ascii")
        }
        mock_post.return_value = mock_response

        response = client.post(
            "/api/tts/preview",
            json={"text": "测试", "model": "mimo-v2.5-tts", "voice": "Mia"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "audio/L16;rate=24000;channels=1"
        assert "preview.pcm" in response.headers["content-disposition"]
        assert response.content == source_audio
