"""Tests for SecretStore — pure env var API key/endpoint resolution."""

from __future__ import annotations

import tempfile

from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore


# ---------------------------------------------------------------------------
# Pure env lookup: get_api_key
# ---------------------------------------------------------------------------

def test_get_api_key_tts_provider() -> None:
    """get_api_key should read provider-specific env var for TTS providers."""
    store = SecretStore(env={"MIMO_API_KEY": "mimo-key-123"})
    assert store.get_api_key("mimo") == "mimo-key-123"

    store2 = SecretStore(env={"DASHSCOPE_API_KEY": "qwen-key-456"})
    assert store2.get_api_key("qwen") == "qwen-key-456"


def test_get_api_key_llm_provider() -> None:
    """get_api_key should read provider-specific env var for LLM providers."""
    store = SecretStore(env={"DEEPSEEK_API_KEY": "sk-deepseek-789"})
    assert store.get_api_key("deepseek") == "sk-deepseek-789"

    store2 = SecretStore(env={"KIMI_API_KEY": "sk-kimi-abc"})
    assert store2.get_api_key("kimi") == "sk-kimi-abc"


def test_get_api_key_vision_provider() -> None:
    """get_api_key should read provider-specific env var for Vision providers."""
    store = SecretStore(env={"XIAOMI_VISION_API_KEY": "xiaomi-vision-key"})
    assert store.get_api_key("xiaomi") == "xiaomi-vision-key"

    store2 = SecretStore(env={"VISION_API_KEY": "openai-vision-key"})
    assert store2.get_api_key("openai") == "openai-vision-key"


def test_get_api_key_fallback_tts() -> None:
    """get_api_key should fallback to TTS_API_KEY for TTS providers."""
    store = SecretStore(env={"TTS_API_KEY": "generic-tts-key"})
    assert store.get_api_key("mimo") == "generic-tts-key"
    assert store.get_api_key("minimax") == "generic-tts-key"
    assert store.get_api_key("qwen") == "generic-tts-key"


def test_get_api_key_fallback_llm() -> None:
    """get_api_key should fallback to LLM_API_KEY for LLM providers."""
    store = SecretStore(env={"LLM_API_KEY": "generic-llm-key"})
    assert store.get_api_key("deepseek") == "generic-llm-key"
    assert store.get_api_key("kimi") == "generic-llm-key"


def test_get_api_key_fallback_vision() -> None:
    """get_api_key should fallback to VISION_API_KEY for Vision providers."""
    store = SecretStore(env={"VISION_API_KEY": "generic-vision-key"})
    assert store.get_api_key("xiaomi") == "generic-vision-key"
    assert store.get_api_key("openai") == "generic-vision-key"
    assert store.get_api_key("claude") == "generic-vision-key"


def test_get_api_key_empty_when_not_set() -> None:
    """get_api_key should return empty string when no env var is set."""
    store = SecretStore(env={})
    assert store.get_api_key("deepseek") == ""
    assert store.get_api_key("mimo") == ""
    assert store.get_api_key("xiaomi") == ""


# ---------------------------------------------------------------------------
# Pure env lookup: get_api_base_url
# ---------------------------------------------------------------------------

def test_get_api_base_url_tts_provider() -> None:
    """get_api_base_url should read provider-specific env var for TTS providers."""
    store = SecretStore(env={"MIMO_API_BASE_URL": "https://mimo.api.com/v1"})
    assert store.get_api_base_url("mimo") == "https://mimo.api.com/v1"


def test_get_api_base_url_llm_provider() -> None:
    """get_api_base_url should read provider-specific env var for LLM providers."""
    store = SecretStore(env={"DEEPSEEK_API_URL": "https://api.deepseek.com/v1"})
    assert store.get_api_base_url("deepseek") == "https://api.deepseek.com/v1"


def test_get_api_base_url_vision_provider() -> None:
    """get_api_base_url should read provider-specific env var for Vision providers."""
    store = SecretStore(env={"XIAOMI_VISION_API_URL": "https://vision.xiaomi.com"})
    assert store.get_api_base_url("xiaomi") == "https://vision.xiaomi.com"

    store2 = SecretStore(env={"VISION_API_URL": "https://vision.openai.com"})
    assert store2.get_api_base_url("openai") == "https://vision.openai.com"


def test_get_api_base_url_fallback_tts() -> None:
    """get_api_base_url should fallback to TTS_API_URL for TTS providers."""
    store = SecretStore(env={"TTS_API_URL": "https://tts.generic.com"})
    assert store.get_api_base_url("mimo") == "https://tts.generic.com"
    assert store.get_api_base_url("minimax") == "https://tts.generic.com"


def test_get_api_base_url_fallback_llm() -> None:
    """get_api_base_url should fallback to LLM_API_URL for LLM providers."""
    store = SecretStore(env={"LLM_API_URL": "https://llm.generic.com"})
    assert store.get_api_base_url("deepseek") == "https://llm.generic.com"
    assert store.get_api_base_url("kimi") == "https://llm.generic.com"


def test_get_api_base_url_fallback_vision() -> None:
    """get_api_base_url should fallback to VISION_API_URL for Vision providers."""
    store = SecretStore(env={"VISION_API_URL": "https://vision.generic.com"})
    assert store.get_api_base_url("xiaomi") == "https://vision.generic.com"
    assert store.get_api_base_url("openai") == "https://vision.generic.com"
    assert store.get_api_base_url("claude") == "https://vision.generic.com"


def test_get_api_base_url_empty_when_not_set() -> None:
    """get_api_base_url should return empty string when no env var is set."""
    store = SecretStore(env={})
    assert store.get_api_base_url("deepseek") == ""
    assert store.get_api_base_url("mimo") == ""
    assert store.get_api_base_url("xiaomi") == ""


def test_get_api_base_url_strips_trailing_slash() -> None:
    """get_api_base_url should strip trailing slash."""
    store = SecretStore(env={"DEEPSEEK_API_URL": "https://api.deepseek.com/v1/"})
    assert store.get_api_base_url("deepseek") == "https://api.deepseek.com/v1"


# ---------------------------------------------------------------------------
# Combo methods (require ConfigReader)
# ---------------------------------------------------------------------------


def test_get_llm_api_key_from_reader() -> None:
    """get_llm_api_key should read provider from ConfigReader and resolve key."""
    store = SecretStore(env={"DEEPSEEK_API_KEY": "sk-deepseek"})
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        assert store.get_llm_api_key(reader) == "sk-deepseek"


def test_get_llm_api_key_provider_specific() -> None:
    """get_llm_api_key should use the default provider (deepseek) from config."""
    store = SecretStore(env={"DEEPSEEK_API_KEY": "sk-deepseek-test"})
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        assert store.get_llm_api_key(reader) == "sk-deepseek-test"


def test_get_llm_endpoint_from_reader() -> None:
    """get_llm_endpoint should read provider from ConfigReader and resolve endpoint."""
    store = SecretStore(env={"DEEPSEEK_API_URL": "https://api.ds.com/v1"})
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        assert store.get_llm_endpoint(reader) == "https://api.ds.com/v1"


def test_get_vision_api_key_from_reader() -> None:
    """get_vision_api_key should read provider from ConfigReader and resolve key."""
    store = SecretStore(env={"XIAOMI_VISION_API_KEY": "viz-key"})
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        assert store.get_vision_api_key(reader) == "viz-key"


def test_get_vision_endpoint_from_reader() -> None:
    """get_vision_endpoint should read provider from ConfigReader and resolve endpoint."""
    store = SecretStore(env={"XIAOMI_VISION_API_URL": "https://viz.api.com"})
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        assert store.get_vision_endpoint(reader) == "https://viz.api.com"


def test_get_vision_model_from_reader() -> None:
    """get_vision_model should read provider from ConfigReader, resolve model."""
    store = SecretStore(env={"XIAOMI_VISION_MODEL": "mimo-v3"})
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        assert store.get_vision_model(reader) == "mimo-v3"


def test_get_vision_model_fallback_to_generic() -> None:
    """get_vision_model should fallback to VISION_MODEL."""
    store = SecretStore(env={"VISION_MODEL": "generic-vision-model"})
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        assert store.get_vision_model(reader) == "generic-vision-model"


def test_combo_methods_accept_product_id() -> None:
    """Combo methods should accept optional product_id forwarded to ConfigReader."""
    store = SecretStore(env={"DEEPSEEK_API_KEY": "sk-by-product"})
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        assert store.get_llm_api_key(reader, product_id="nonexistent") == "sk-by-product"


# ---------------------------------------------------------------------------
# vision_client.py migration
# ---------------------------------------------------------------------------


def test_resolve_vision_config_with_secret_store() -> None:
    """resolve_vision_config should accept optional SecretStore + ConfigReader."""
    from packages.pipeline_services.asset_library.vision_client import (
        resolve_vision_config,
    )

    store = SecretStore(
        env={
            "XIAOMI_VISION_API_KEY": "injected-vision-key",
            "XIAOMI_VISION_API_URL": "https://injected.api.com",
            "XIAOMI_VISION_MODEL": "injected-model",
        }
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        result = resolve_vision_config({}, secrets=store, reader=reader)
        assert result["api_key"] == "injected-vision-key"
        assert result["endpoint"] == "https://injected.api.com"
        assert result["model"] == "injected-model"
        assert result["provider"] == "xiaomi"
