"""测试 optimize_text_preview 配置字段"""
from packages.provider_config.tts_config import TTSConfig


def test_tts_config_has_optimize_text_preview():
    config = TTSConfig()
    assert hasattr(config, "optimize_text_preview")


def test_optimize_text_preview_default_false():
    config = TTSConfig()
    assert config.optimize_text_preview is False


def test_optimize_text_preview_to_dict():
    config = TTSConfig(optimize_text_preview=True)
    config_dict = config.to_dict()
    assert config_dict["optimize_text_preview"] is True


def test_optimize_text_preview_from_dict():
    data = {"optimize_text_preview": True}
    config = TTSConfig.from_dict(data)
    assert config.optimize_text_preview is True
