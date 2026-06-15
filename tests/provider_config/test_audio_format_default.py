"""测试音频格式默认值修复"""
from packages.provider_config.tts_config import TTSConfig, TTSConfigManager
from packages.provider_config.app_config import DEFAULTS


def test_tts_config_default_audio_format():
    """TTSConfig 默认音频格式应为 wav"""
    config = TTSConfigManager()
    default_config = config.get_config()
    assert default_config.audio_format == "wav", f"Expected 'wav', got '{default_config.audio_format}'"


def test_app_config_defaults_audio_format():
    """AppConfigManager DEFAULTS 中 tts 音频格式应为 wav"""
    assert DEFAULTS["tts"]["audio_format"] == "wav", f"Expected 'wav', got '{DEFAULTS['tts']['audio_format']}'"


def test_tts_config_with_defaults_audio_format():
    """TTSConfig.with_defaults() 应返回 wav"""
    config = TTSConfig()
    config_with_defaults = config.with_defaults()
    assert config_with_defaults.audio_format == "wav"
