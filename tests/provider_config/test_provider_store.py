from __future__ import annotations

import json

import yaml

from packages.provider_config.catalog import default_provider_document
from packages.provider_config.store import load_provider_config, save_provider_config


def test_save_provider_config_uses_app_config_as_runtime_source(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    app_config_path = config_dir / "app_config.json"
    app_config_path.write_text(
        json.dumps({"media": {"ffmpeg_path": "custom-ffmpeg"}}),
        encoding="utf-8",
    )
    payload = load_provider_config(tmp_path)
    # Use LLM section since TTS is now managed exclusively via /api/tts/config (#386)
    payload["providers"]["llm"]["selected"] = "deepseek"
    payload["providers"]["llm"]["providers"]["deepseek"].update(
        {
            "endpoint": "https://deepseek.example.com/api",
            "model": "deepseek-v4-pro",
        }
    )

    save_provider_config(tmp_path, payload)

    assert not (config_dir / "providers.yaml").exists()
    saved = json.loads(app_config_path.read_text(encoding="utf-8"))
    assert saved["llm"]["provider"] == "deepseek"
    assert saved["llm"]["model"] == "deepseek-v4-pro"
    assert saved["llm"]["endpoint"] == "https://deepseek.example.com/api"
    assert saved["media"]["ffmpeg_path"] == "custom-ffmpeg"
    assert "deepseek" not in saved.get("provider_profiles", {}).get("llm", {})


def test_app_config_wins_over_stale_legacy_provider_yaml(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    legacy = default_provider_document()
    legacy["providers"]["llm"]["selected"] = "openai"
    legacy["providers"]["llm"]["providers"]["openai"]["model"] = "gpt-4o"
    (config_dir / "providers.yaml").write_text(
        yaml.safe_dump(legacy, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (config_dir / "app_config.json").write_text(
        json.dumps(
            {
                "llm": {
                    "provider": "deepseek",
                    "model": "deepseek-v4-pro",
                    "endpoint": "https://deepseek.example.com/api",
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = load_provider_config(tmp_path)

    assert loaded["providers"]["llm"]["selected"] == "deepseek"
    assert (
        loaded["providers"]["llm"]["providers"]["deepseek"]["model"]
        == "deepseek-v4-pro"
    )
    assert (
        loaded["providers"]["llm"]["providers"]["deepseek"]["endpoint"]
        == "https://deepseek.example.com/api"
    )


def test_existing_app_config_uses_catalog_defaults_for_missing_sections(
    tmp_path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    legacy = default_provider_document()
    legacy["providers"]["llm"]["selected"] = "openai"
    (config_dir / "providers.yaml").write_text(
        yaml.safe_dump(legacy, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (config_dir / "app_config.json").write_text(
        json.dumps({"media": {"ffmpeg_path": "custom-ffmpeg"}}),
        encoding="utf-8",
    )

    loaded = load_provider_config(tmp_path)

    assert loaded["providers"]["llm"]["selected"] == "deepseek"
    # TTS section should be empty since it's managed separately (#386)
    assert loaded["providers"]["tts"]["providers"] == {}


def test_save_provider_config_keeps_secret_only_in_env(tmp_path) -> None:
    payload = default_provider_document()
    payload["providers"]["llm"]["selected"] = "deepseek"
    payload["providers"]["llm"]["providers"]["deepseek"]["api_key"] = "secret-value"

    save_provider_config(tmp_path, payload)

    app_config = (tmp_path / "config" / "app_config.json").read_text(encoding="utf-8")
    env_file = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "secret-value" not in app_config
    assert "DEEPSEEK_API_KEY=secret-value" in env_file
    assert (
        load_provider_config(tmp_path)["providers"]["llm"]["providers"]["deepseek"][
            "api_key"
        ]
        == "***"
    )
