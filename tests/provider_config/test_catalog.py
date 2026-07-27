from packages.provider_config.catalog import (
    default_runtime_provider_config,
    default_runtime_settings,
    provider_field_to_runtime_field,
    provider_options_payload,
    tts_connection_fields,
    tts_models,
    tts_provider_for_model,
    tts_runtime_providers,
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
    assert tts_runtime_providers() == {"qwen", "mimo"}
    assert tts_provider_for_model("qwen3-tts-instruct-flash") == "qwen"
    assert tts_provider_for_model("mimo-v2.5-tts-voiceclone") == "mimo"
    assert tts_provider_for_model("speech-2.8-hd") is None
    assert tts_provider_for_model("custom-tts-v1") is None
    assert provider_field_to_runtime_field("style") == "style_prompt"


def test_provider_form_hints_are_served_from_catalog() -> None:
    hints = provider_options_payload()["field_hints"]

    assert hints["api_key"].startswith("仅保存在 .env")
    assert hints["model"] == "当前 provider 实际调用的模型"


def test_user_configurable_runtime_defaults_have_one_catalog_source() -> None:
    settings = default_runtime_settings()

    for section in ("embedding", "media", "asset_library", "scene"):
        for field, value in settings[section].items():
            assert DEFAULTS[section][field] == value


def test_tts_models_are_served_from_catalog() -> None:
    models = tts_models()

    by_model = {m["model"]: m for m in models}
    assert set(by_model) == {
        "qwen3-tts-flash",
        "qwen3-tts-instruct-flash",
        "mimo-v2.5-tts",
        "mimo-v2.5-tts-voicedesign",
        "mimo-v2.5-tts-voiceclone",
    }
    assert by_model["qwen3-tts-flash"]["provider"] == "qwen"
    assert "preset_voice" in by_model["qwen3-tts-flash"]["features"]
    assert "instruct" in by_model["qwen3-tts-instruct-flash"]["features"]
    assert "voice_design" in by_model["mimo-v2.5-tts-voicedesign"]["features"]
    assert "voice_clone" in by_model["mimo-v2.5-tts-voiceclone"]["features"]
    # Every declared model must route back to its provider.
    for m in models:
        assert tts_provider_for_model(m["model"]) == m["provider"]


def test_tts_connection_fields_are_derived_from_catalog() -> None:
    assert tts_connection_fields("qwen") == ["endpoint", "extra_headers"]
    assert tts_connection_fields("mimo") == [
        "endpoint",
        "group_id",
        "speed",
        "vol",
        "pitch",
        "emotion",
        "extra_headers",
    ]
    assert tts_connection_fields("unknown") == []
