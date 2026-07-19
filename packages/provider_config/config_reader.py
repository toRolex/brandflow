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
    _set_nested,
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


# Lazy import avoids circular dependency: secret_store imports ConfigReader.
from packages.provider_config.secret_store import SecretStore  # noqa: E402


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
        from packages.pipeline_services.asset_library.category_config import (
            get_categories as category_config_get_categories,
        )

        cats = category_config_get_categories(
            self._reader, product_id=self._product_id(product_id)
        )
        return [c.name for c in cats if c.name]

    def category_suggestion_model(self) -> str:
        """Return the model used for asset category suggestions."""
        return self._reader.get_category_suggestion_model()

    @property
    def secrets(self) -> SecretStore:
        """Expose the underlying SecretStore for seam factories."""
        return self._secrets

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


class ProductStore:
    """CRUD operations for products stored in ``app_config.json``.

    Parameters:
        reader: A ``ConfigReader`` instance whose ``reload()`` is called after writes.
        config_path: Path to the ``app_config.json`` file.
    """

    def __init__(self, reader: Any, config_path: Path) -> None:
        self._reader = reader
        self._config_path = config_path

    @property
    def active_id(self) -> str:
        """Return the current active product ID."""
        return self._reader.active_product_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self) -> dict[str, Any]:
        """Read the raw JSON config from disk."""
        return load_config(self._config_path)

    def _save(self, data: dict[str, Any]) -> None:
        """Atomically persist *data* and refresh the reader cache."""
        save_config(self._config_path, data)
        self._reader.reload()

    def _ensure_active_product(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Ensure ``products`` list and active product exist for write ops."""
        if "products" not in raw:
            raw["products"] = []
        if "active_product_id" not in raw:
            raw["active_product_id"] = ""

        if not raw["active_product_id"] and raw["products"]:
            raw["active_product_id"] = raw["products"][0]["id"]

        if not raw["products"]:
            raw["products"] = [{"id": "default"}]
            raw["active_product_id"] = "default"

        return raw

    # ------------------------------------------------------------------
    # Product CRUD
    # ------------------------------------------------------------------

    def create_product(self, name: str) -> dict[str, str]:
        """Create a new product. *name* doubles as the product ID (cannot be empty)."""
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("product name cannot be empty")

        raw = self._load()
        if "products" not in raw:
            raw["products"] = []

        for p in raw["products"]:
            if p.get("id") == trimmed:
                return {"id": trimmed, "name": trimmed}

        raw["products"].append({"id": trimmed, "default_name": trimmed})
        raw["active_product_id"] = trimmed

        self._save(raw)
        return {"id": trimmed, "name": trimmed}

    def list_products(self) -> list[dict[str, str]]:
        """Return id + name summaries for every known product."""
        raw = self._load()
        products = raw.get("products", [])
        return [
            {
                "id": p.get("id", ""),
                "name": p.get("default_name", "")
                or p.get("name", "")
                or p.get("id", ""),
            }
            for p in products
        ]

    def switch_product(self, product_id: str) -> None:
        """Switch the active product, creating it when it does not exist."""
        raw = self._load()
        if "products" not in raw:
            raw["products"] = []

        found = any(p.get("id") == product_id for p in raw["products"])
        if not found:
            raw["products"].append({"id": product_id})

        raw["active_product_id"] = product_id
        self._save(raw)

    def rename_product(self, product_id: str, name: str) -> dict[str, str]:
        """Rename a product by updating its ``default_name``.  Does NOT change the ID."""
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("product name cannot be empty")

        raw = self._load()
        for i, p in enumerate(raw.get("products", [])):
            if p.get("id") == product_id:
                raw["products"][i]["default_name"] = trimmed
                self._save(raw)
                return {"id": product_id, "name": trimmed}

        raise ValueError("product not found")

    def delete_product(self, product_id: str) -> dict[str, str | None]:
        """Delete a product.  Auto-selects a new active product when the active one is deleted."""
        raw = self._load()
        products = raw.get("products", [])

        index = None
        for i, p in enumerate(products):
            if p.get("id") == product_id:
                index = i
                break

        if index is None:
            raise ValueError("product not found")

        was_active = raw.get("active_product_id") == product_id
        products.pop(index)

        new_active = raw.get("active_product_id")
        if was_active:
            if products:
                new_active = products[0]["id"]
            else:
                new_active = ""
            raw["active_product_id"] = new_active

        self._save(raw)
        return {"status": "deleted", "active_product_id": new_active}

    def resolve_product_name(self, explicit_product: str = "") -> str:
        """Resolve product name with fallback chain.

        Priority: explicit_product > active product name > default_name > id.
        Returns empty string when no active product is configured.
        """
        if explicit_product:
            return explicit_product
        config = self.get_product_config()
        name = config.get("name", "")
        if name:
            return name
        default = config.get("default_name", "")
        if default:
            return default
        return config.get("id", "")

    # ------------------------------------------------------------------
    # Product config writes
    # ------------------------------------------------------------------

    def set_product_config(self, values: dict[str, Any]) -> None:
        """Write *values* (deep-merged) into the active product config."""
        raw = self._load()
        self._ensure_active_product(raw)
        active_id = raw.get("active_product_id", "")

        for i, p in enumerate(raw["products"]):
            if p.get("id") == active_id:
                existing = raw["products"][i]
                merged = _deep_merge(existing, values)
                merged.pop("name", None)
                raw["products"][i] = merged
                break

        self._save(raw)

    def save_product_config(self, product_id: str, values: dict[str, Any]) -> None:
        """Write *values* into a specific product's config (creates product when missing)."""
        raw = self._load()
        self._ensure_active_product(raw)

        for i, p in enumerate(raw["products"]):
            if p.get("id") == product_id:
                existing = raw["products"][i]
                merged = _deep_merge(existing, values)
                merged["id"] = product_id
                merged.pop("name", None)
                raw["products"][i] = merged
                self._save(raw)
                return

        raw["products"].append({"id": product_id, **values})
        self._save(raw)

    def reset_product_config(self) -> None:
        """Reset the active product's config to defaults. Keep the product entity."""
        raw = self._load()
        active_id = raw.get("active_product_id", "")

        for i, p in enumerate(raw.get("products", [])):
            if p.get("id") == active_id:
                raw["products"][i] = {"id": active_id}
                break

        self._save(raw)

    def set_product(self, key: str, value: Any) -> None:
        """Set a dot-path field on the active product."""
        raw = self._load()
        self._ensure_active_product(raw)
        active_id = raw.get("active_product_id", "")

        for i, p in enumerate(raw["products"]):
            if p.get("id") == active_id:
                _set_nested(raw["products"][i], key, value)
                break

        self._save(raw)

    # ------------------------------------------------------------------
    # Product config access (delegated to reader for reads)
    # ------------------------------------------------------------------

    def get_product_config(self, product_id: str | None = None) -> dict[str, Any]:
        """Return the merged config for *product_id* (or the active product)."""
        self._reader.reload()
        if product_id:
            return self._reader.get_product_config(product_id=product_id)

        active = self._reader.active_product_id
        if active:
            return self._reader.get_product_config(product_id=active)
        return self._reader.get_product_config()
