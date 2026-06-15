from __future__ import annotations

from unittest.mock import MagicMock, patch

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


class TestMiMoTTSProviderSynthesize:
    def _make_provider(self):
        return MiMoTTSProvider(api_key="test-key", base_url="https://api.xiaomimimo.com/v1")

    def _mock_config(self, **overrides):
        config = MagicMock()
        config.model = "mimo-v2.5-tts"
        config.voice = "Mia"
        config.fallback_voice = "Dean"
        config.randomize_voice = False
        config.random_voices = ["Mia", "Dean"]
        config.style_control_mode = "simple"
        config.style_prompt = "自然 清晰"
        config.voice_design_prompt = ""
        config.audio_format = "wav"
        config.audio_tags_enabled = False
        config.audio_tags = ""
        for k, v in overrides.items():
            setattr(config, k, v)
        return config

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_returns_audio_bytes(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"audio": {"data": "dGVzdA=="}}}]
        }
        mock_resp.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_resp

        provider = self._make_provider()
        audio = provider.synthesize("测试文本", self._mock_config())
        assert isinstance(audio, bytes)
        assert len(audio) > 0

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_raises_quota_on_429(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.raise_for_status.side_effect = Exception("Rate limited")
        mock_requests.post.return_value = mock_resp

        provider = self._make_provider()
        with pytest.raises(TTSQuotaExceededError):
            provider.synthesize("测试", self._mock_config())

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_raises_blocked_on_401(self, mock_requests):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status.side_effect = Exception("Unauthorized")
        mock_requests.post.return_value = mock_resp

        provider = self._make_provider()
        with pytest.raises(TTSBlockedError):
            provider.synthesize("测试", self._mock_config())
