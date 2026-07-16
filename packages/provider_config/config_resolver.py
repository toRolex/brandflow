"""ConfigResolver — high-level config queries for phase handlers.

Wraps ``ConfigReader`` + ``SecretStore`` and exposes a small, phase-oriented
API: ``tts()``, ``llm()``, and ``categories()``.
"""

from __future__ import annotations

from typing import Any

from packages.pipeline_services.asset_library.category_config import (
    get_categories as category_config_get_categories,
)
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore


class ConfigResolver:
    """Resolve merged config + secrets for pipeline phase handlers.

    Parameters
    ----------
    reader:
        ConfigReader instance (required).
    secrets:
        SecretStore instance.  A fresh instance is created when omitted.
    """

    def __init__(
        self,
        *,
        reader: ConfigReader,
        secrets: SecretStore | None = None,
    ) -> None:
        self._reader = reader
        self._secrets = secrets if secrets is not None else SecretStore()

    # ------------------------------------------------------------------
    # Public phase-oriented API
    # ------------------------------------------------------------------

    def tts(self, product_id: str = "") -> dict[str, Any]:
        """Return merged TTS config for *product_id* (empty = root defaults)."""
        return self._reader.get_tts_config(product_id=self._product_id(product_id))

    def llm(self, product_id: str = "") -> tuple[dict[str, Any], str, str]:
        """Return merged LLM config, API key, and chat-completions URL.

        The returned ``api_url`` has ``/chat/completions`` appended when the
        configured base URL does not already end with it.
        """
        config = self._reader.get_llm_config(product_id=self._product_id(product_id))
        provider = config.get("provider", "deepseek")
        api_key = self._api_key_for(provider)
        api_url = self._chat_completions_url_for(provider)
        return config, api_key, api_url

    def categories(self, product_id: str = "") -> list[str]:
        """Return category name list for *product_id*.

        Delegates to ``category_config.get_categories()`` and strips entries
        with empty names.
        """
        cats = category_config_get_categories(
            self._reader, product_id=self._product_id(product_id)
        )
        return [c.name for c in cats if c.name]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _product_id(product_id: str) -> str | None:
        """Normalize empty product_id to None for ConfigReader compatibility."""
        return product_id or None

    def _api_key_for(self, provider: str) -> str:
        """Resolve API key for *provider* via SecretStore."""
        return self._secrets.get_api_key(provider)

    def _api_base_url_for(self, provider: str) -> str:
        """Resolve base API URL for *provider* via SecretStore."""
        return self._secrets.get_api_base_url(provider)

    def _chat_completions_url_for(self, provider: str) -> str:
        """Resolve chat-completions URL for *provider*, auto-completing the path."""
        url = self._api_base_url_for(provider)
        if url and not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        return url
