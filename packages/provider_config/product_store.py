"""Product CRUD store extracted from AppConfigManager (now ConfigReader).

All writes go through ``config_io.save_config()`` and call ``self._reader.reload()``
to keep the ConfigReader hot-cache in sync.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.provider_config.config_io import load_config, save_config


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
        if "active_product_id" not in raw or not raw["active_product_id"]:
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
        from packages.provider_config.config_constants import _deep_merge

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
        from packages.provider_config.config_constants import _deep_merge

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
        """Remove the active product and re-select a new active (or clear)."""
        raw = self._load()
        active_id = raw.get("active_product_id", "")

        products = raw.get("products", [])
        for i, p in enumerate(products):
            if p.get("id") == active_id:
                products.pop(i)
                break

        if products:
            raw["active_product_id"] = products[0]["id"]
        else:
            raw["active_product_id"] = ""

        self._save(raw)

    def set_product(self, key: str, value: Any) -> None:
        """Set a dot-path field on the active product."""
        from packages.provider_config.config_constants import _set_nested

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
