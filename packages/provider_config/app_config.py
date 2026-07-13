"""Shared config constants and helpers.

``DEFAULTS`` is the single source of truth for default configuration values.
``_deep_merge``, ``_get_nested``, and ``_set_nested`` are low-level utility
functions used throughout the config layer.

New code should use ``ConfigReader``, ``ProductStore``, and ``SecretStore`` directly.
"""

from __future__ import annotations

from packages.provider_config.config_constants import (
    DEFAULTS,
    _deep_merge,
    _get_nested,
    _set_nested,
)

# Backward compatibility: tests monkeypatch this attribute to prevent
# ``dotenv.load_dotenv()`` from running during isolated test sessions.
load_dotenv = None

__all__ = ["DEFAULTS", "_deep_merge", "_get_nested", "_set_nested"]
