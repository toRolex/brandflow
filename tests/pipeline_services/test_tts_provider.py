import pytest
from packages.pipeline_services.tts_provider import (
    TTSError,
    TTSRetryableError,
    TTSBlockedError,
    TTSQuotaExceededError,
    MiMoTTSProvider,
)
from packages.provider_config.tts_config import TTSConfig


class TestTTSErrors:
    def test_tts_error_hierarchy(self):
        assert issubclass(TTSRetryableError, TTSError)
        assert issubclass(TTSBlockedError, TTSError)
        assert issubclass(TTSQuotaExceededError, TTSBlockedError)

    def test_raise_retryable_error(self):
        with pytest.raises(TTSRetryableError):
            raise TTSRetryableError("rate limited")

    def test_raise_blocked_error(self):
        with pytest.raises(TTSBlockedError):
            raise TTSBlockedError("auth failed")

    def test_raise_quota_error(self):
        with pytest.raises(TTSQuotaExceededError):
            raise TTSQuotaExceededError("quota exceeded")


class TestMiMoTTSProvider:
    def test_provider_initialization(self):
        provider = MiMoTTSProvider(api_key="test_key")
        assert provider.api_key == "test_key"
        assert provider.base_url == "https://api.xiaomimimo.com/v1"

    def test_build_preset_request(self):
        provider = MiMoTTSProvider(api_key="test_key")
        config = TTSConfig(
            model="mimo-v2.5-tts",
            voice="Mia",
            style_prompt="活泼热情"
        )

        request = provider._build_request(
            text="测试文本",
            config=config,
            voice_id="Mia"
        )

        assert request["model"] == "mimo-v2.5-tts"
        assert request["audio"]["voice"] == "Mia"
        assert len(request["messages"]) == 2
        assert request["messages"][0]["role"] == "user"
        assert "活泼热情" in request["messages"][0]["content"]
        assert request["messages"][1]["content"] == "测试文本"

    def test_build_voicedesign_request(self):
        provider = MiMoTTSProvider(api_key="test_key")
        config = TTSConfig(
            model="mimo-v2.5-tts-voicedesign",
            voice_design_prompt="年轻女性，声音甜美清澈"
        )

        request = provider._build_request(
            text="测试文本",
            config=config
        )

        assert request["model"] == "mimo-v2.5-tts-voicedesign"
        assert "voice" not in request.get("audio", {})
        assert request["messages"][0]["content"] == "年轻女性，声音甜美清澈"
