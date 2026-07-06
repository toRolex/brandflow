"""Configurable asset category definition.

Replaces the hardcoded ``Category`` enum for new code.
Old code may continue using ``Category`` for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass


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
