from packages.provider_config.catalog import (
    default_runtime_provider_config,
    provider_field_to_runtime_field,
    provider_options_payload,
    tts_provider_for_model,
)
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


def test_tts_runtime_contract_is_declared_by_catalog() -> None:
    options = provider_options_payload()["providers"]["tts"]["providers"]

    assert set(options) == {"qwen", "mimo"}
    assert tts_provider_for_model("qwen3-tts-instruct-flash") == "qwen"
    assert tts_provider_for_model("mimo-v2.5-tts-voiceclone") == "mimo"
    assert tts_provider_for_model("speech-2.8-hd") is None
    assert provider_field_to_runtime_field("style") == "style_prompt"


def test_provider_form_hints_are_served_from_catalog() -> None:
    hints = provider_options_payload()["field_hints"]

    assert hints["api_key"].startswith("仅保存在 .env")
    assert hints["model"] == "当前 provider 实际调用的模型"
