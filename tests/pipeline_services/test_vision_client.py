from __future__ import annotations

import os
from unittest.mock import patch

from packages.pipeline_services.asset_library.vision_client import resolve_vision_config


def test_resolve_vision_config_from_app_config(monkeypatch) -> None:
    """resolve_vision_config 应从 AppConfigManager 读取配置"""
    monkeypatch.setenv("XIAOMI_VISION_API_KEY", "test-key")
    monkeypatch.setenv("XIAOMI_VISION_API_URL", "https://api.example.com/v1/chat/completions")
    monkeypatch.setenv("XIAOMI_VISION_MODEL", "mimo-v2.5")

    with patch(
        "packages.provider_config.app_config.AppConfigManager._load",
        return_value={},
    ):
        config = resolve_vision_config({})

    assert config["provider"] == "xiaomi"
    assert config["api_key"] == "test-key"
    assert config["endpoint"] == "https://api.example.com/v1/chat/completions"
    assert config["model"] == "mimo-v2.5"
