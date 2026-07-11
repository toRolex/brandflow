"""SecretStore — pure env var API key / endpoint resolution.

No dependency on config files. All methods that need a provider name
take it directly; combo methods accept a ``ConfigReader`` to extract
the provider name from the config.
"""

from __future__ import annotations

import os
from typing import Any

from packages.provider_config.config_reader import ConfigReader


class SecretStore:
    """Resolve API keys and endpoints from environment variables."""

    API_KEY_ENV_MAP = {
        "mimo": "MIMO_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
        "minimax": "MINIMAX_API_KEY",
        "xiaomi": "XIAOMI_VISION_API_KEY",
        "openai": "VISION_API_KEY",
        "claude": "VISION_API_KEY",
    }

    API_BASE_URL_ENV_MAP = {
        "mimo": "MIMO_API_BASE_URL",
        "qwen": "DASHSCOPE_API_URL",
        "deepseek": "DEEPSEEK_API_URL",
        "kimi": "KIMI_API_URL",
        "minimax": "MINIMAX_TTS_URL",
        "xiaomi": "XIAOMI_VISION_API_URL",
        "openai": "VISION_API_URL",
        "claude": "VISION_API_URL",
    }

    VISION_MODEL_ENV_MAP = {
        "xiaomi": "XIAOMI_VISION_MODEL",
        "openai": "VISION_MODEL",
        "claude": "VISION_MODEL",
    }

    _TTS_PROVIDERS = frozenset({"mimo", "minimax", "qwen"})
    _LLM_PROVIDERS = frozenset({"deepseek", "kimi"})
    _VISION_PROVIDERS = frozenset({"xiaomi", "openai", "claude"})

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ

    # ------------------------------------------------------------------
    # Pure env lookup (no ConfigReader)
    # ------------------------------------------------------------------

    def get_api_key(self, provider: str) -> str:
        """Return the API key for *provider* from env vars.

        Priority: provider-specific env var -> category fallback.
        """
        env_key = self.API_KEY_ENV_MAP.get(provider, "")
        value = self._env.get(env_key, "").strip().strip('"').strip("'")
        if not value:
            if provider in self._TTS_PROVIDERS:
                value = self._env.get("TTS_API_KEY", "").strip().strip('"').strip("'")
            elif provider in self._VISION_PROVIDERS:
                value = self._env.get("VISION_API_KEY", "").strip().strip('"').strip("'")
            else:
                value = self._env.get("LLM_API_KEY", "").strip().strip('"').strip("'")
        return value

    def get_api_base_url(self, provider: str) -> str:
        """Return the API base URL for *provider* from env vars.

        Priority: provider-specific env var -> category fallback.
        Trailing slashes are stripped.
        """
        env_key = self.API_BASE_URL_ENV_MAP.get(provider, "")
        value = self._env.get(env_key, "").strip().rstrip("/")
        if not value:
            if provider in self._TTS_PROVIDERS:
                value = self._env.get("TTS_API_URL", "").strip().rstrip("/")
            elif provider in self._VISION_PROVIDERS:
                value = self._env.get("VISION_API_URL", "").strip().rstrip("/")
            elif provider in self._LLM_PROVIDERS:
                value = self._env.get("LLM_API_URL", "").strip().rstrip("/")
        return value

    # ------------------------------------------------------------------
    # Combo methods (require ConfigReader)
    # ------------------------------------------------------------------

    def get_llm_api_key(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the LLM API key by reading the active provider from config."""
        config = reader.get_llm_config(product_id=product_id)
        provider = config.get("provider", "deepseek")
        return self.get_api_key(provider)

    def get_llm_endpoint(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the LLM endpoint by reading the active provider from config."""
        config = reader.get_llm_config(product_id=product_id)
        provider = config.get("provider", "deepseek")
        return self.get_api_base_url(provider)

    def get_vision_api_key(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the Vision API key by reading the active provider from config."""
        config = reader.get_vision_config(product_id=product_id)
        provider = config.get("provider", "xiaomi")
        return self.get_api_key(provider)

    def get_vision_endpoint(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the Vision endpoint by reading the active provider from config."""
        config = reader.get_vision_config(product_id=product_id)
        provider = config.get("provider", "xiaomi")
        return self.get_api_base_url(provider)

    def get_vision_model(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the Vision model from env vars, with provider-specific fallback.

        Reads env var: provider-specific VISION_MODEL -> generic VISION_MODEL.
        """
        config = reader.get_vision_config(product_id=product_id)
        provider = config.get("provider", "xiaomi")
        env_key = self.VISION_MODEL_ENV_MAP.get(provider, "VISION_MODEL")
        value = self._env.get(env_key, "").strip()
        if not value:
            value = self._env.get("VISION_MODEL", "").strip()
        return value
