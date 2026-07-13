from __future__ import annotations

from unittest.mock import patch

from packages.pipeline_services.asset_library.vision_client import (
    VisionClient,
    resolve_vision_config,
)


def test_build_openai_request_max_tokens_is_2000() -> None:
    """_build_openai_request 的 max_tokens 应为 2000（避免 MiMo reasoning 模型输出截断）"""
    client = VisionClient(
        api_key="key",
        endpoint="https://api.example.com/v1",
        model="mimo-v2.5",
        provider="openai",
    )
    payload, _headers = client._build_openai_request("data:image/jpeg;base64,abc")
    assert payload["max_tokens"] == 2000


def test_build_claude_request_max_tokens_is_2000() -> None:
    """_build_claude_request 的 max_tokens 应为 2000"""
    client = VisionClient(
        api_key="key",
        endpoint="https://api.example.com/v1",
        model="claude-sonnet",
        provider="claude",
    )
    payload, _headers = client._build_claude_request("abc", "image/jpeg")
    assert payload["max_tokens"] == 2000


def test_resolve_endpoint_appends_suffix_when_missing() -> None:
    """endpoint 不以 /chat/completions 结尾时自动追加"""
    client = VisionClient(
        api_key="key",
        endpoint="https://api.example.com/v1",
        model="mimo-v2.5",
        provider="openai",
    )
    assert client._resolve_endpoint() == "https://api.example.com/v1/chat/completions"


def test_resolve_endpoint_handles_trailing_slash() -> None:
    """尾部带 / 时正确处理"""
    client = VisionClient(
        api_key="key",
        endpoint="https://api.example.com/v1/",
        model="mimo-v2.5",
        provider="openai",
    )
    assert client._resolve_endpoint() == "https://api.example.com/v1/chat/completions"


def test_resolve_endpoint_no_duplicate() -> None:
    """已以 /chat/completions 结尾时不重复追加"""
    client = VisionClient(
        api_key="key",
        endpoint="https://api.example.com/v1/chat/completions",
        model="mimo-v2.5",
        provider="openai",
    )
    assert client._resolve_endpoint() == "https://api.example.com/v1/chat/completions"


def test_resolve_vision_config_from_app_config(monkeypatch) -> None:
    """resolve_vision_config 应从 ConfigReader 读取配置"""
    monkeypatch.setenv("XIAOMI_VISION_API_KEY", "test-key")
    monkeypatch.setenv(
        "XIAOMI_VISION_API_URL", "https://api.example.com/v1/chat/completions"
    )
    monkeypatch.setenv("XIAOMI_VISION_MODEL", "mimo-v2.5")

    with patch(
        "packages.provider_config.config_io.load_config",
        return_value={},
    ):
        config = resolve_vision_config({})

    assert config["provider"] == "xiaomi"
    assert config["api_key"] == "test-key"
    assert config["endpoint"] == "https://api.example.com/v1/chat/completions"
    assert config["model"] == "mimo-v2.5"
