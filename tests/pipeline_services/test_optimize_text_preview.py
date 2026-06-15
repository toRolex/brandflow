"""测试 optimize_text_preview 参数"""
from packages.pipeline_services.tts_provider import MiMoTTSProvider
from packages.provider_config.tts_config import TTSConfig


def test_voicedesign_request_with_optimize_text_preview():
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts-voicedesign",
        voice_design_prompt="年轻女声",
        audio_format="wav",
        optimize_text_preview=True,
    )
    request = provider._build_voicedesign_request("测试文本", config)
    assert request["audio"].get("optimize_text_preview") is True


def test_voicedesign_request_without_optimize_text_preview():
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts-voicedesign",
        voice_design_prompt="年轻女声",
        audio_format="wav",
        optimize_text_preview=False,
    )
    request = provider._build_voicedesign_request("测试文本", config)
    assert "optimize_text_preview" not in request["audio"]
