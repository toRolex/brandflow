"""白盒测试：关心代码覆盖率和内部逻辑"""

from packages.provider_config.tts_config import TTSConfig, TTSConfigManager
from packages.pipeline_services.tts_provider import (
    TTSError,
    TTSRetryableError,
    TTSBlockedError,
    TTSQuotaExceededError,
    MiMoTTSProvider,
)


class TestTTSConfigWhiteBox:
    def test_to_dict_covers_all_fields(self):
        config = TTSConfig(
            model="test",
            voice="v",
            fallback_voice="fv",
            randomize_voice=False,
            random_voices=["A"],
            voice_design_prompt="vdp",
            style_prompt="sp",
            audio_format="wav",
            sample_rate=44100,
            bitrate=192000,
            channel=2,
            enable_request_logging=True,
            enable_performance_metrics=False,
            log_audio_duration=False,
        )
        data = config.to_dict()
        assert len(data) == 26
        assert data["model"] == "test"
        assert data["voice"] == "v"
        assert data["fallback_voice"] == "fv"
        assert data["randomize_voice"] is False
        assert data["random_voices"] == ["A"]
        assert data["voice_design_prompt"] == "vdp"
        assert data["style_prompt"] == "sp"
        assert data["audio_format"] == "wav"
        assert data["sample_rate"] == 44100
        assert data["bitrate"] == 192000
        assert data["channel"] == 2
        assert data["enable_request_logging"] is True
        assert data["enable_performance_metrics"] is False
        assert data["log_audio_duration"] is False

    def test_from_dict_handles_missing_keys(self):
        config = TTSConfig.from_dict({})
        assert config.model is None
        assert config.voice is None

    def test_with_defaults_preserves_all_set_values(self):
        config = TTSConfig(
            model="m",
            voice="v",
            fallback_voice="fv",
            randomize_voice=False,
            random_voices=["A"],
            voice_design_prompt="vdp",
            style_prompt="sp",
            audio_format="wav",
            sample_rate=44100,
            bitrate=192000,
            channel=2,
            enable_request_logging=True,
            enable_performance_metrics=False,
            log_audio_duration=False,
        )
        with_defaults = config.with_defaults()
        assert with_defaults.model == "m"
        assert with_defaults.voice == "v"
        assert with_defaults.fallback_voice == "fv"
        assert with_defaults.randomize_voice is False
        assert with_defaults.random_voices == ["A"]
        assert with_defaults.voice_design_prompt == "vdp"
        assert with_defaults.style_prompt == "sp"
        assert with_defaults.audio_format == "wav"
        assert with_defaults.sample_rate == 44100
        assert with_defaults.bitrate == 192000
        assert with_defaults.channel == 2
        assert with_defaults.enable_request_logging is True
        assert with_defaults.enable_performance_metrics is False
        assert with_defaults.log_audio_duration is False

    def test_merge_configs_priority_chain(self):
        c1 = TTSConfig(model="m1", voice="v1", sample_rate=None)
        c2 = TTSConfig(model="m2", style_prompt="s2")
        c3 = TTSConfig(model="m3", sample_rate=44100)
        merged = TTSConfigManager._merge_configs(c1, c2, c3)
        assert merged.model == "m3"
        assert merged.voice == "v1"
        assert merged.style_prompt == "s2"
        assert merged.sample_rate == 44100


class TestMiMoTTSProviderWhiteBox:
    def test_error_hierarchy_depth(self):
        assert issubclass(TTSRetryableError, TTSError)
        assert issubclass(TTSBlockedError, TTSError)
        assert issubclass(TTSQuotaExceededError, TTSBlockedError)
        assert issubclass(TTSQuotaExceededError, TTSError)

    def test_build_preset_request_structure(self):
        provider = MiMoTTSProvider(api_key="test")
        config = TTSConfig(model="mimo-v2.5-tts", voice="Mia", style_prompt="自然")
        request = provider._build_request("text", config, "Mia")
        assert "model" in request
        assert "messages" in request
        assert "audio" in request
        assert "stream" in request
        assert len(request["messages"]) == 2
        assert request["messages"][0]["role"] == "user"
        assert request["messages"][1]["role"] == "assistant"
        assert request["audio"]["voice"] == "Mia"

    def test_build_voicedesign_request_no_voice(self):
        provider = MiMoTTSProvider(api_key="test")
        config = TTSConfig(
            model="mimo-v2.5-tts-voicedesign", voice_design_prompt="prompt"
        )
        request = provider._build_request("text", config)
        assert "voice" not in request.get("audio", {})
        assert request["messages"][0]["content"] == "prompt"
