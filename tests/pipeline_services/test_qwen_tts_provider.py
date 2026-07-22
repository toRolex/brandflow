from unittest.mock import patch, Mock
import pytest
from packages.pipeline_services.tts_provider import (
    QwenTTSProvider,
    TTSBlockedError,
    TTSQuotaExceededError,
)


class FakeConfig:
    def __init__(self, **kwargs):
        defaults = {
            "model": "qwen3-tts-flash",
            "voice": "Rocky",
            "language_type": "Chinese",
            "instructions": "",
            "optimize_instructions": False,
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


QWEN_RESPONSE = {
    "output": {
        "audio": {
            "url": "https://dashscope-result.oss-cn-beijing.aliyuncs.com/audio.wav",
            "id": "audio_xxx",
            "expires_at": 9999999999,
        }
    },
    "usage": {"characters": 50},
}

FAKE_AUDIO = b"RIFF\x00\x00\x00\x00WAVEfake"


class TestQwenTTSProvider:
    def test_synthesize_basic(self):
        """合成文本，验证返回音频 bytes"""
        provider = QwenTTSProvider(api_key="sk-test")
        config = FakeConfig()

        with patch.object(provider, "_http_post") as mock_post:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = QWEN_RESPONSE
            mock_resp.raise_for_status = Mock()
            mock_post.return_value = mock_resp

            with patch("requests.get") as mock_get:
                mock_get_resp = Mock()
                mock_get_resp.content = FAKE_AUDIO
                mock_get_resp.raise_for_status = Mock()
                mock_get.return_value = mock_get_resp

                result = provider.synthesize("你好世界", config)
                assert result == FAKE_AUDIO
                assert mock_get.call_args.kwargs["proxies"]["all"] is None

    def test_synthesize_with_instructions(self):
        """instruct 模型 + instructions + optimize_instructions"""
        provider = QwenTTSProvider(api_key="sk-test")
        config = FakeConfig(
            model="qwen3-tts-instruct-flash",
            instructions="语速较快，热情洋溢",
            optimize_instructions=True,
        )

        with patch.object(provider, "_http_post") as mock_post:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = QWEN_RESPONSE
            mock_resp.raise_for_status = Mock()
            mock_post.return_value = mock_resp

            with patch("requests.get") as mock_get:
                mock_get_resp = Mock()
                mock_get_resp.content = FAKE_AUDIO
                mock_get_resp.raise_for_status = Mock()
                mock_get.return_value = mock_get_resp

                result = provider.synthesize("你好世界", config)
                assert result == FAKE_AUDIO

                call_args = mock_post.call_args
                assert call_args is not None
                payload = call_args.args[0]
                assert payload["input"]["instructions"] == "语速较快，热情洋溢"
                assert payload["input"]["optimize_instructions"] is True

    def test_synthesize_api_error(self):
        """API 返回错误码"""
        provider = QwenTTSProvider(api_key="sk-test")
        config = FakeConfig()

        with patch.object(provider, "_http_post") as mock_post:
            mock_resp = Mock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "code": "InvalidApiKey",
                "message": "bad key",
            }
            mock_resp.raise_for_status = Mock()
            mock_post.return_value = mock_resp

            with pytest.raises(TTSBlockedError):
                provider.synthesize("test", config)

    def test_synthesize_quota_exceeded(self):
        """HTTP 429 配额超限"""
        provider = QwenTTSProvider(api_key="sk-test")
        config = FakeConfig()

        with patch.object(provider, "_http_post") as mock_post:
            mock_resp = Mock()
            mock_resp.status_code = 429
            mock_resp.raise_for_status = Mock()
            mock_post.return_value = mock_resp

            with pytest.raises(TTSQuotaExceededError):
                provider.synthesize("test", config)

    def test_synthesize_auth_error(self):
        """HTTP 401/403 鉴权失败"""
        provider = QwenTTSProvider(api_key="sk-test")
        config = FakeConfig()

        for status in (401, 403):
            with patch.object(provider, "_http_post") as mock_post:
                mock_resp = Mock()
                mock_resp.status_code = status
                mock_resp.raise_for_status = Mock()
                mock_post.return_value = mock_resp

                with pytest.raises(TTSBlockedError):
                    provider.synthesize("test", config)

    def test_build_payload_defaults(self):
        """默认配置 payload 结构"""
        provider = QwenTTSProvider(api_key="sk-test")
        config = FakeConfig()
        payload = provider._build_payload("你好", config)

        assert payload["model"] == "qwen3-tts-flash"
        assert payload["input"]["text"] == "你好"
        assert payload["input"]["voice"] == "Rocky"
        assert payload["input"]["language_type"] == "Chinese"
        assert "instructions" not in payload["input"]

    def test_build_payload_with_language(self):
        """指定 language_type"""
        provider = QwenTTSProvider(api_key="sk-test")
        config = FakeConfig(language_type="English")
        payload = provider._build_payload("hello", config)

        assert payload["input"]["language_type"] == "English"
