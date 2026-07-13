"""Configurable asset category definition.

Replaces the hardcoded ``Category`` enum for new code.
Old code may continue using ``Category`` for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.provider_config.config_reader import ConfigReader


@dataclass
class CategoryConfig:
    """A single configurable category for asset classification.

    Parameters
    ----------
    id:
        Machine-readable short identifier (e.g. ``"origin"``, ``"stir_fry"``).
    name:
        Human-readable Chinese category name (e.g. ``"产地溯源"``, ``"烹饪翻炒"``).
    description:
        Optional longer description of what this category covers.
    vision_prompt:
        Optional vision-specific prompt hint for this category.
    """

    id: str
    name: str
    description: str = ""
    vision_prompt: str = ""


def default_categories() -> list[CategoryConfig]:
    """Return legacy food categories for backward compatibility.

    These match the deprecated ``Category`` enum and are used as a fallback when
    no instance- or product-level categories are configured.
    """
    return [
        CategoryConfig(id="origin", name="产地溯源"),
        CategoryConfig(id="sorting", name="筛选分拣"),
        CategoryConfig(id="washing", name="清洗泡发"),
        CategoryConfig(id="cutting", name="切配处理"),
        CategoryConfig(id="into_wok", name="下锅入锅"),
        CategoryConfig(id="stir_fry", name="烹饪翻炒"),
        CategoryConfig(id="plating", name="出锅装盘"),
        CategoryConfig(id="finished", name="成品展示"),
        CategoryConfig(id="tasting", name="试吃品尝"),
        CategoryConfig(id="macro", name="产品特写"),
    ]


def _dict_to_category_config(d: dict) -> CategoryConfig:
    """Convert a raw dict to a CategoryConfig."""
    return CategoryConfig(
        id=d.get("id", ""),
        name=d.get("name", ""),
        description=d.get("description", ""),
        vision_prompt=d.get("vision_prompt", ""),
    )


def get_categories(
    reader: "ConfigReader", product_id: str | None = None
) -> list[CategoryConfig]:
    """Return the configured asset categories with priority chain.

    Priority chain:
    1. ``product.categories`` (product-level override)
    2. ``asset_library.categories`` (instance-level)
    3. ``default_categories()`` (food fallback)

    Args:
        reader: A ``ConfigReader`` instance.
        product_id: Optional product ID. When None, uses active product.

    Returns:
        List of ``CategoryConfig`` instances.
    """
    # Priority 1: product-level categories
    product_config = reader.get_product_config(product_id=product_id)
    product_cats: list[dict] = product_config.get("categories", [])
    if product_cats:
        return [_dict_to_category_config(c) for c in product_cats]

    # Priority 2: asset_library categories (instance-level)
    al_config = reader.get_asset_library_config()
    raw: list[dict] = al_config.get("categories", [])
    if raw:
        return [_dict_to_category_config(c) for c in raw]

    # Priority 3: default food categories
    return default_categories()
