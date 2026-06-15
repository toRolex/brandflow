"""测试 voiceclone 配置字段"""
from packages.provider_config.tts_config import TTSConfig


def test_tts_config_has_voiceclone_fields():
    config = TTSConfig()
    assert hasattr(config, "voice_clone_sample_path")
    assert hasattr(config, "voice_clone_mime_type")


def test_tts_config_voiceclone_defaults():
    config = TTSConfig()
    assert config.voice_clone_sample_path is None
    assert config.voice_clone_mime_type is None


def test_tts_config_voiceclone_to_dict():
    config = TTSConfig(
        voice_clone_sample_path="voice_clone_sample.mp3",
        voice_clone_mime_type="audio/mpeg"
    )
    config_dict = config.to_dict()
    assert config_dict["voice_clone_sample_path"] == "voice_clone_sample.mp3"
    assert config_dict["voice_clone_mime_type"] == "audio/mpeg"


def test_tts_config_voiceclone_from_dict():
    data = {
        "voice_clone_sample_path": "voice_clone_sample.mp3",
        "voice_clone_mime_type": "audio/wav"
    }
    config = TTSConfig.from_dict(data)
    assert config.voice_clone_sample_path == "voice_clone_sample.mp3"
    assert config.voice_clone_mime_type == "audio/wav"
