"""Pure config reader with hot-cache on construction.

Reads ``config/app_config.json`` once, runs ``_migrate_if_needed``, walks every
product and builds a three-layer-merged cache (DEFAULTS -> root -> product-override).
All ``get_*()`` methods are O(1) dict lookups after construction.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from packages.provider_config.config_constants import (
    DEFAULTS,
    _deep_merge,
    _get_nested,
)
from packages.provider_config.config_io import load_config, save_config


class ConfigReader:
    """Read and cache every config section from ``app_config.json``.

    Parameters:
        config_dir: Directory that contains ``app_config.json``.
    """

    def __init__(self, config_dir: str | Path = "config") -> None:
        self._config_dir = Path(config_dir)
        self._config_path = self._config_dir / "app_config.json"
        self._lock = threading.Lock()
        self._raw: dict[str, Any] = {}
        self._cache: dict[str, dict[str, Any]] = {}
        self._product_cache: dict[str, dict[str, dict[str, Any]]] = {}
        self._build_cache()

    # ------------------------------------------------------------------
    # Public read API
    # ------------------------------------------------------------------

    @property
    def active_product_id(self) -> str:
        """Return the ``active_product_id`` from the raw config, or empty string."""
        with self._lock:
            return self._raw.get("active_product_id", "")

    def get(self, section: str, product_id: str | None = None) -> dict[str, Any]:
        """Return merged config for *section*.

        When *product_id* is given and the section has product-level overrides,
        the product-specific merged config is returned.  If *section* is unknown,
        an empty dict is returned.
        """
        with self._lock:
            if section not in self._cache:
                return {}
            if product_id and product_id in self._product_cache:
                return self._product_cache[product_id].get(
                    section, self._cache[section]
                )
            return self._cache[section]

    def get_tts_config(self, product_id: str | None = None) -> dict[str, Any]:
        """Return TTS config.  When *product_id* is given, product overrides are applied."""
        return self.get("tts", product_id=product_id)

    def get_llm_config(self, product_id: str | None = None) -> dict[str, Any]:
        """Return LLM config.  When *product_id* is given, product overrides are applied."""
        return self.get("llm", product_id=product_id)

    def get_vision_config(self, product_id: str | None = None) -> dict[str, Any]:
        """Return Vision config.  When *product_id* is given, product overrides are applied."""
        return self.get("vision", product_id=product_id)

    def get_scene_config(self, product_id: str | None = None) -> dict[str, Any]:
        """Return Scene config.  Product-level scene overrides top-level scene."""
        return self.get("scene", product_id=product_id)

    def get_media_config(self) -> dict[str, Any]:
        """Return media config (no product override)."""
        return self.get("media")

    def get_video_config(self) -> dict[str, Any]:
        """Return video config (no product override)."""
        return self.get("video")

    def get_asset_library_config(self) -> dict[str, Any]:
        """Return asset-library config (no product override)."""
        return self.get("asset_library")

    def get_product_config(self, product_id: str | None = None) -> dict[str, Any]:
        """Return product config for *product_id* (or root-default when None)."""
        return self.get("product", product_id=product_id)

    def get_product_value(
        self, key: str, default: Any = None, product_id: str | None = None
    ) -> Any:
        """Return a nested value from the product config via dot-path key."""
        config = self.get_product_config(product_id=product_id)
        return _get_nested(config, key, default)

    def get_keyword_map(self, product_id: str | None = None) -> dict[str, list[str]]:
        """Return keyword-to-category mapping for the given product."""
        config = self.get_product_config(product_id=product_id)
        raw = config.get("keyword_map", {})
        if not isinstance(raw, dict):
            return {}
        return {str(k): list(v) for k, v in raw.items() if isinstance(v, list)}

    def get_category_suggestion_model(self) -> str:
        """Return the model used for category suggestions."""
        al = self.get_asset_library_config()
        return al.get("category_suggestion_model", "deepseek-v4-flash")

    def get_category_suggestion_sample_size(self) -> int:
        """Return the sample size for category suggestions."""
        al = self.get_asset_library_config()
        return al.get("category_suggestion_sample_size", 20)

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """Re-read the config file from disk and rebuild the full cache."""
        self._build_cache()

    # ------------------------------------------------------------------
    # Internal: cache building
    # ------------------------------------------------------------------

    def _build_cache(self) -> None:
        """Load config file, migrate, merge, and populate in-memory caches."""
        raw = self._load_and_migrate()
        self._raw = raw if isinstance(raw, dict) else {}

        root = raw if isinstance(raw, dict) else {}
        products: list[dict[str, Any]] = root.get("products", [])

        # -- root-level merged configs (DEFAULTS + root section) ---------
        self._cache = {
            "tts": _deep_merge(DEFAULTS["tts"], root.get("tts", {})),
            "llm": _deep_merge(DEFAULTS["llm"], root.get("llm", {})),
            "vision": _deep_merge(DEFAULTS["vision"], root.get("vision", {})),
            "scene": _deep_merge(DEFAULTS["scene"], root.get("scene", {})),
            "media": _deep_merge(DEFAULTS["media"], root.get("media", {})),
            "video": _deep_merge(DEFAULTS["video"], root.get("video", {})),
            "asset_library": _deep_merge(
                DEFAULTS["asset_library"], root.get("asset_library", {})
            ),
            "product": _deep_merge(DEFAULTS["product"], root.get("product", {})),
        }

        # -- per-product cache (DEFAULTS + root-section + product-override)
        self._product_cache = {}
        for p in products:
            pid = p.get("id", "")
            if not pid:
                continue

            root_product = self._cache["product"]

            # Build full product config: DEFAULTS.product + root.product + p
            product_merged = _deep_merge(root_product, p)
            product_merged.setdefault("id", pid)
            if not product_merged.get("name"):
                product_merged["name"] = product_merged.get(
                    "default_name", ""
                ) or product_merged.get("id", "")

            # Scene: product-level scene overrides top-level scene
            p_scene = p.get("scene")
            if isinstance(p_scene, dict) and p_scene:
                scene_merged = _deep_merge(DEFAULTS["scene"], p_scene)
            else:
                scene_merged = self._cache["scene"]

            self._product_cache[pid] = {
                "tts": _deep_merge(
                    self._cache["tts"],
                    p.get("tts", {}) if isinstance(p.get("tts"), dict) else {},
                ),
                "llm": _deep_merge(
                    self._cache["llm"],
                    p.get("llm", {}) if isinstance(p.get("llm"), dict) else {},
                ),
                "vision": _deep_merge(
                    self._cache["vision"],
                    p.get("vision", {}) if isinstance(p.get("vision"), dict) else {},
                ),
                "scene": scene_merged,
                "product": product_merged,
            }

    def _load_and_migrate(self) -> dict[str, Any]:
        """Load raw config and apply schema migration if needed."""
        raw = load_config(self._config_path)

        # Migrate old "product" -> "products" (one-time, write-back)
        if "product" in raw and "products" not in raw:
            old_product = raw.pop("product", {})
            raw["products"] = [{"id": "default", **old_product}]
            raw["active_product_id"] = "default"
            save_config(self._config_path, raw)

        return raw
