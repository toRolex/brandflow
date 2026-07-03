"""Configurable asset category definition.

Replaces the hardcoded ``Category`` enum for new code.
Old code may continue using ``Category`` for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    """Return the default food-related categories matching the legacy ``Category`` enum."""
    return [
        CategoryConfig(id="origin", name="产地溯源", description="产地溯源场景"),
        CategoryConfig(id="sorting", name="筛选分拣", description="筛选分拣场景"),
        CategoryConfig(id="washing", name="清洗泡发", description="清洗泡发场景"),
        CategoryConfig(id="cutting", name="切配处理", description="切配处理场景"),
        CategoryConfig(id="into_wok", name="下锅入锅", description="下锅入锅场景"),
        CategoryConfig(id="stir_fry", name="烹饪翻炒", description="烹饪翻炒场景"),
        CategoryConfig(id="plating", name="出锅装盘", description="出锅装盘场景"),
        CategoryConfig(id="finished", name="成品展示", description="成品展示场景"),
        CategoryConfig(id="tasting", name="试吃品尝", description="试吃品尝场景"),
        CategoryConfig(id="macro", name="产品特写", description="产品特写场景"),
    ]
