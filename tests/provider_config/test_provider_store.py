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
    payload["providers"]["tts"]["selected"] = "qwen"
    payload["providers"]["tts"]["providers"]["qwen"].update(
        {
            "endpoint": "https://qwen.example.com/api",
            "model": "qwen3-tts-flash",
            "voice": "Cherry",
        }
    )

    save_provider_config(tmp_path, payload)

    assert not (config_dir / "providers.yaml").exists()
    saved = json.loads(app_config_path.read_text(encoding="utf-8"))
    assert saved["tts"]["provider"] == "qwen"
    assert saved["tts"]["model"] == "qwen3-tts-flash"
    assert saved["tts"]["endpoint"] == "https://qwen.example.com/api"
    assert saved["tts"]["voice"] == "Cherry"
    assert saved["media"]["ffmpeg_path"] == "custom-ffmpeg"
    assert "qwen" not in saved["provider_profiles"]["tts"]


def test_app_config_wins_over_stale_legacy_provider_yaml(tmp_path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    legacy = default_provider_document()
    legacy["providers"]["tts"]["selected"] = "mimo"
    legacy["providers"]["tts"]["providers"]["mimo"]["model"] = "mimo-v2.5-tts"
    (config_dir / "providers.yaml").write_text(
        yaml.safe_dump(legacy, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (config_dir / "app_config.json").write_text(
        json.dumps(
            {
                "tts": {
                    "provider": "qwen",
                    "model": "qwen3-tts-flash",
                    "endpoint": "https://qwen.example.com/api",
                }
            }
        ),
        encoding="utf-8",
    )

    loaded = load_provider_config(tmp_path)

    assert loaded["providers"]["tts"]["selected"] == "qwen"
    assert loaded["providers"]["tts"]["providers"]["qwen"]["model"] == "qwen3-tts-flash"
    assert (
        loaded["providers"]["tts"]["providers"]["qwen"]["endpoint"]
        == "https://qwen.example.com/api"
    )


def test_existing_app_config_uses_catalog_defaults_for_missing_sections(
    tmp_path,
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    legacy = default_provider_document()
    legacy["providers"]["tts"]["selected"] = "mimo"
    (config_dir / "providers.yaml").write_text(
        yaml.safe_dump(legacy, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (config_dir / "app_config.json").write_text(
        json.dumps({"media": {"ffmpeg_path": "custom-ffmpeg"}}),
        encoding="utf-8",
    )

    loaded = load_provider_config(tmp_path)

    assert loaded["providers"]["tts"]["selected"] == "qwen"


def test_save_provider_config_keeps_secret_only_in_env(tmp_path) -> None:
    payload = default_provider_document()
    payload["providers"]["tts"]["selected"] = "qwen"
    payload["providers"]["tts"]["providers"]["qwen"]["api_key"] = "secret-value"

    save_provider_config(tmp_path, payload)

    app_config = (tmp_path / "config" / "app_config.json").read_text(encoding="utf-8")
    env_file = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "secret-value" not in app_config
    assert "DASHSCOPE_API_KEY=secret-value" in env_file
    assert (
        load_provider_config(tmp_path)["providers"]["tts"]["providers"]["qwen"][
            "api_key"
        ]
        == "***"
    )
