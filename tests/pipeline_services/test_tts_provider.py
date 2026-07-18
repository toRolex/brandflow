from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock, patch
import wave

import pytest

from packages.pipeline_services.tts_provider import (
    TTSError,
    TTSRetryableError,
    TTSBlockedError,
    TTSQuotaExceededError,
    MiMoTTSProvider,
    QwenTTSProvider,
    create_tts_provider,
)
from packages.provider_config.secret_store import SecretStore
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
        config = TTSConfig(model="mimo-v2.5-tts", voice="Mia", style_prompt="活泼热情")

        request = provider._build_request(
            text="测试文本", config=config, voice_id="Mia"
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
            voice_design_prompt="年轻女性，声音甜美清澈",
        )

        request = provider._build_request(text="测试文本", config=config)

        assert request["model"] == "mimo-v2.5-tts-voicedesign"
        assert "voice" not in request.get("audio", {})
        assert request["messages"][0]["content"] == "年轻女性，声音甜美清澈"


class TestMiMoTTSProviderSynthesize:
    @staticmethod
    def _wav_bytes() -> bytes:
        output = io.BytesIO()
        with wave.open(output, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(b"\x00\x00" * 240)
        return output.getvalue()

    def _make_provider(self):
        return MiMoTTSProvider(
            api_key="test-key", base_url="https://api.xiaomimimo.com/v1"
        )

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
    def test_synthesize_decodes_nested_audio_data_byte_for_byte(self, mock_requests):
        source_audio = self._wav_bytes()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
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
        mock_requests.post.return_value = mock_resp

        audio = self._make_provider().synthesize("test", self._mock_config())

        assert audio == source_audio

    @pytest.mark.parametrize("field", ["audio", "data", "b64_json", "base64"])
    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_accepts_supported_direct_string_fields(
        self, mock_requests, field
    ):
        source_audio = self._wav_bytes()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            field: base64.b64encode(source_audio).decode("ascii")
        }
        mock_requests.post.return_value = mock_resp

        assert (
            self._make_provider().synthesize("test", self._mock_config())
            == source_audio
        )

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_recurses_through_audio_objects_and_lists(self, mock_requests):
        source_audio = self._wav_bytes()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "result": {
                "audio": [
                    {"metadata": {"ignored": True}},
                    {"payload": {"data": base64.b64encode(source_audio).decode()}},
                ]
            }
        }
        mock_requests.post.return_value = mock_resp

        assert (
            self._make_provider().synthesize("test", self._mock_config())
            == source_audio
        )

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_decodes_data_uri(self, mock_requests):
        source_audio = self._wav_bytes()
        encoded = base64.b64encode(source_audio).decode("ascii")
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"audio": f"data:audio/wav;base64,{encoded}"}
        mock_requests.post.return_value = mock_resp

        assert (
            self._make_provider().synthesize("test", self._mock_config())
            == source_audio
        )

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_prefers_strict_base64_for_hex_shaped_string(
        self, mock_requests
    ):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"audio": "AAAA"}
        mock_requests.post.return_value = mock_resp

        assert (
            self._make_provider().synthesize(
                "test", self._mock_config(audio_format="pcm16")
            )
            == b"\x00\x00\x00"
        )

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_decodes_explicit_hex(self, mock_requests):
        source_audio = self._wav_bytes()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"audio": f"hex:{source_audio.hex()}"}
        mock_requests.post.return_value = mock_resp

        assert (
            self._make_provider().synthesize("test", self._mock_config())
            == source_audio
        )

    @pytest.mark.parametrize(
        "response_body",
        [
            {"audio": "not*valid*base64=="},
            {"audio": "dGVzdA="},
            {"audio": {"metadata": "not audio"}},
            {"choices": [{"message": {"content": "no audio"}}]},
        ],
    )
    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_rejects_invalid_or_missing_audio(
        self, mock_requests, response_body
    ):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = response_body
        mock_requests.post.return_value = mock_resp

        with pytest.raises(TTSBlockedError, match="valid audio data") as exc_info:
            self._make_provider().synthesize("test", self._mock_config())

        assert "not audio" not in str(exc_info.value)
        assert "not*valid" not in str(exc_info.value)

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_sanitizes_invalid_json_response(self, mock_requests):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.side_effect = ValueError("secret raw provider response")
        mock_requests.post.return_value = mock_resp

        with pytest.raises(TTSBlockedError, match="invalid response") as exc_info:
            self._make_provider().synthesize("test", self._mock_config())

        assert "secret raw provider response" not in str(exc_info.value)

    @patch("packages.pipeline_services.tts_provider.requests")
    def test_synthesize_sanitizes_provider_error(self, mock_requests):
        mock_resp = MagicMock(status_code=400)
        mock_resp.json.return_value = {
            "error": "request rejected; api-key=secret-provider-key"
        }
        mock_requests.post.return_value = mock_resp

        with pytest.raises(TTSBlockedError, match="HTTP 400") as exc_info:
            self._make_provider().synthesize("test", self._mock_config())

        assert "secret-provider-key" not in str(exc_info.value)

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


class TestCreateTTSProvider:
    """Factory selects provider by model prefix and resolves secrets."""

    def test_qwen_prefix_returns_qwen_provider(self):
        secrets = SecretStore(
            env={
                "DASHSCOPE_API_KEY": "qwen-key",
                "DASHSCOPE_API_URL": "https://qwen.example.com",
            }
        )
        provider = create_tts_provider({"model": "qwen3-tts-flash"}, secrets)
        assert isinstance(provider, QwenTTSProvider)
        assert provider.api_key == "qwen-key"
        assert provider.base_url == "https://qwen.example.com"

    def test_mimo_prefix_returns_mimo_provider(self):
        secrets = SecretStore(
            env={
                "MIMO_API_KEY": "mimo-key",
                "MIMO_API_BASE_URL": "https://mimo.example.com",
            }
        )
        provider = create_tts_provider({"model": "mimo-v2.5-tts"}, secrets)
        assert isinstance(provider, MiMoTTSProvider)
        assert provider.api_key == "mimo-key"
        assert provider.base_url == "https://mimo.example.com"

    def test_empty_model_defaults_to_mimo(self):
        secrets = SecretStore(env={"MIMO_API_KEY": "mimo-key"})
        provider = create_tts_provider({}, secrets)
        assert isinstance(provider, MiMoTTSProvider)
        assert provider.api_key == "mimo-key"
        assert provider.base_url == "https://api.xiaomimimo.com/v1"

    def test_fallback_base_url_when_env_missing(self):
        secrets = SecretStore(env={"DASHSCOPE_API_KEY": "qwen-key"})
        provider = create_tts_provider({"model": "qwen-tts"}, secrets)
        assert isinstance(provider, QwenTTSProvider)
        assert provider.base_url == "https://dashscope.aliyuncs.com/api/v1"

    def test_tts_api_key_fallback(self):
        secrets = SecretStore(env={"TTS_API_KEY": "fallback-key"})
        provider = create_tts_provider({"model": "mimo-v2.5-tts"}, secrets)
        assert isinstance(provider, MiMoTTSProvider)
        assert provider.api_key == "fallback-key"


# ---------------------------------------------------------------------------
# TTSConfigShim — regression guard: missing flat keys must not crash
# ---------------------------------------------------------------------------


class TestTTSConfigShimDefaults:
    """TTSConfigShim supplies defaults for all optional flat attributes."""

    def test_empty_dict_gets_all_defaults(self):
        """Empty dict → every expected attribute gets its default value."""
        from packages.pipeline_services.tts_provider import TTSConfigShim

        shim = TTSConfigShim({})
        assert shim.model == "mimo-v2.5-tts"
        assert shim.voice == "Mia"
        assert shim.style_control_mode == "simple"
        assert shim.style_prompt == "自然 清晰"
        assert shim.audio_format == "wav"
        assert shim.director_character == ""
        assert shim.director_scene == ""
        assert shim.director_guidance == ""
        assert shim.audio_tags_enabled is False
        assert shim.audio_tags == ""

    def test_missing_nested_keys_get_defaults(self):
        """A config dict with nested director/audio_tags but no flat keys
        must supply defaults for the flat key access that MiMo provider uses."""
        from packages.pipeline_services.tts_provider import TTSConfigShim

        cfg = {
            "model": "mimo-v2.5-tts",
            "voice": "Mia",
            "director": {
                "character": "女主播",
                "scene": "直播间",
                "guidance": "语速适中",
            },
            "audio_tags": {"enabled": True, "tags": "(温柔)"},
        }
        shim = TTSConfigShim(cfg)
        # Flat keys that don't exist in dict get defaults
        assert shim.director_character == ""
        assert shim.director_scene == ""
        assert shim.director_guidance == ""
        assert shim.audio_tags_enabled is False
        # audio_tags key exists as nested dict in input – shim returns dict as-is
        # ponytail: no flattening, see AC
        assert isinstance(shim.audio_tags, dict)
        # Explicitly set keys are preserved
        assert shim.model == "mimo-v2.5-tts"
        assert shim.voice == "Mia"

    def test_flat_keys_are_preserved(self):
        """When the dict has flat keys, those values are used."""
        from packages.pipeline_services.tts_provider import TTSConfigShim

        cfg = {
            "model": "qwen-tts",
            "voice": "Cherry",
            "director_character": "男主播",
            "audio_tags_enabled": True,
        }
        shim = TTSConfigShim(cfg)
        assert shim.model == "qwen-tts"
        assert shim.voice == "Cherry"
        assert shim.director_character == "男主播"
        assert shim.audio_tags_enabled is True
