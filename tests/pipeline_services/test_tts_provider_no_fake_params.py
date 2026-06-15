"""测试 TTS provider 不发送 API 不支持的参数"""
from packages.pipeline_services.tts_provider import MiMoTTSProvider
from packages.provider_config.tts_config import TTSConfig


def test_preset_request_no_sample_rate():
    """预置音色请求不应包含 sample_rate"""
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts",
        voice="Mia",
        audio_format="wav",
        sample_rate=32000,
    )
    request = provider._build_preset_request("测试文本", config)
    assert "sample_rate" not in request.get("audio", {}), "sample_rate 不应出现在请求中"


def test_preset_request_no_bitrate():
    """预置音色请求不应包含 bitrate"""
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts",
        voice="Mia",
        audio_format="wav",
        bitrate=128000,
    )
    request = provider._build_preset_request("测试文本", config)
    assert "bitrate" not in request.get("audio", {}), "bitrate 不应出现在请求中"


def test_preset_request_no_channel():
    """预置音色请求不应包含 channel"""
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts",
        voice="Mia",
        audio_format="wav",
        channel=1,
    )
    request = provider._build_preset_request("测试文本", config)
    assert "channel" not in request.get("audio", {}), "channel 不应出现在请求中"


def test_voicedesign_request_no_fake_params():
    """音色设计请求也不应包含虚假参数"""
    provider = MiMoTTSProvider(api_key="test_key")
    config = TTSConfig(
        model="mimo-v2.5-tts-voicedesign",
        voice_design_prompt="年轻女声",
        audio_format="wav",
        sample_rate=32000,
        bitrate=128000,
        channel=1,
    )
    request = provider._build_voicedesign_request("测试文本", config)
    audio = request.get("audio", {})
    assert "sample_rate" not in audio
    assert "bitrate" not in audio
    assert "channel" not in audio
