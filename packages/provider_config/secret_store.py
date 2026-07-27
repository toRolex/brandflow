"""SecretStore — pure env var API key / endpoint resolution.

No dependency on config files. All methods that need a provider name
take it directly; combo methods accept a ``ConfigReader`` to extract
the provider name from the config.
"""

from __future__ import annotations

import os

from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.runtime_env import (
    LLM_ENV_MAPPINGS,
    TTS_ENV_MAPPINGS,
    VISION_ENV_MAPPINGS,
)


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
        "custom": "CUSTOM_API_KEY",
        "embedding": "EMBEDDING_API_KEY",
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
        "custom": "CUSTOM_API_URL",
        "embedding": "EMBEDDING_API_URL",
    }

    VISION_MODEL_ENV_MAP = {
        "xiaomi": "XIAOMI_VISION_MODEL",
        "openai": "VISION_MODEL",
        "claude": "VISION_MODEL",
    }

    _TTS_PROVIDERS = frozenset({"mimo", "minimax", "qwen"})
    _LLM_PROVIDERS = frozenset({"deepseek", "kimi", "openai", "custom"})
    _VISION_PROVIDERS = frozenset({"xiaomi", "claude"})

    def __init__(self, env: dict[str, str] | None = None) -> None:
        self._env = env if env is not None else os.environ

    # ------------------------------------------------------------------
    # Pure env lookup (no ConfigReader)
    # ------------------------------------------------------------------

    @staticmethod
    def _mapped_env_name(section: str, provider: str, field_name: str) -> str:
        mappings = {
            "llm": LLM_ENV_MAPPINGS,
            "tts": TTS_ENV_MAPPINGS,
            "vision": VISION_ENV_MAPPINGS,
        }.get(section, {})
        for env_name, mapped_field in mappings.get(provider, {}).get("env", {}).items():
            if mapped_field == field_name:
                return env_name
        return ""

    def get_api_key(self, provider: str, section: str = "") -> str:
        """Return the API key for *provider* from env vars.

        Priority: provider-specific env var -> category fallback.
        """
        env_key = self._mapped_env_name(section, provider, "api_key")
        if not env_key:
            env_key = self.API_KEY_ENV_MAP.get(provider, "")
        value = self._env.get(env_key, "").strip().strip('"').strip("'")
        if not value:
            if provider in self._TTS_PROVIDERS:
                value = self._env.get("TTS_API_KEY", "").strip().strip('"').strip("'")
            elif provider in self._VISION_PROVIDERS:
                value = (
                    self._env.get("VISION_API_KEY", "").strip().strip('"').strip("'")
                )
            else:
                value = self._env.get("LLM_API_KEY", "").strip().strip('"').strip("'")
        return value

    def get_api_base_url(self, provider: str, section: str = "") -> str:
        """Return the API base URL for *provider* from env vars.

        Priority: provider-specific env var -> category fallback.
        Trailing slashes are stripped.
        """
        env_key = self._mapped_env_name(section, provider, "endpoint")
        if not env_key:
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
        return self.get_api_key(provider, section="llm")

    def get_llm_endpoint(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the configured LLM endpoint, with legacy env fallback."""
        config = reader.get_llm_config(product_id=product_id)
        provider = config.get("provider", "deepseek")
        return str(config.get("endpoint") or "").strip().rstrip(
            "/"
        ) or self.get_api_base_url(provider, section="llm")

    def get_vision_api_key(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the Vision API key by reading the active provider from config."""
        config = reader.get_vision_config(product_id=product_id)
        provider = config.get("provider", "xiaomi")
        return self.get_api_key(provider, section="vision")

    def get_vision_endpoint(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the configured Vision endpoint, with legacy env fallback."""
        config = reader.get_vision_config(product_id=product_id)
        provider = config.get("provider", "xiaomi")
        return str(config.get("endpoint") or "").strip().rstrip(
            "/"
        ) or self.get_api_base_url(provider, section="vision")

    def get_vision_model(
        self, reader: ConfigReader, product_id: str | None = None
    ) -> str:
        """Return the non-secret Vision model from app_config."""
        config = reader.get_vision_config(product_id=product_id)
        return str(config.get("model") or "").strip()
