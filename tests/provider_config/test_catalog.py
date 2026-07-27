from packages.provider_config.catalog import default_runtime_provider_config
from packages.provider_config.config_constants import DEFAULTS


def test_provider_runtime_defaults_have_one_catalog_source() -> None:
    runtime_defaults = default_runtime_provider_config()

    assert runtime_defaults["llm"]["provider"] == "deepseek"
    assert runtime_defaults["llm"]["model"] == "deepseek-v4-pro"
    assert runtime_defaults["tts"]["provider"] == "qwen"
    assert runtime_defaults["tts"]["model"] == "qwen3-tts-flash"
    assert runtime_defaults["vision"]["provider"] == "xiaomi"
    assert runtime_defaults["vision"]["model"] == "mimo-v2.5"

    for section in ("llm", "tts", "vision"):
        for field, value in runtime_defaults[section].items():
            assert DEFAULTS[section][field] == value
