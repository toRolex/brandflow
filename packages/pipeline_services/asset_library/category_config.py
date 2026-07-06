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
    """Return default categories. Returns empty list — categories should come from product config."""
    return []
