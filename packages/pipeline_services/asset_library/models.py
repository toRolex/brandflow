from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Category(str, Enum):
    """Deprecated: use ``CategoryConfig`` from ``category_config.py`` instead.

    This enum is retained for backward compatibility with existing indexed assets.
    New code should prefer ``CategoryConfig`` from
    ``packages.pipeline_services.asset_library.category_config``.
    """

    ORIGIN = "产地溯源"
    SORTING = "筛选分拣"
    WASHING = "清洗泡发"
    CUTTING = "切配处理"
    INTO_WOK = "下锅入锅"
    STIR_FRY = "烹饪翻炒"
    PLATING = "出锅装盘"
    FINISHED = "成品展示"
    TASTING = "试吃品尝"
    MACRO = "产品特写"


AssetStatus = Literal["pending_review", "available", "disabled"]


class AssetRecord(BaseModel):
    asset_id: str
    file_path: str
    category: Category
    product: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    duration_seconds: float = 0.0
    status: AssetStatus = "available"
    usage_count: int = 0
    source_video: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str = ""
    last_used_at: str = ""

    def category_name(self) -> str:
        """Return the category value as a plain string.

        Works with both deprecated ``Category`` enum and config-based string categories.
        """
        if isinstance(self.category, Category):
            return self.category.value
        return str(self.category)


def load_keyword_map() -> dict[str, list[str]]:
    """Load the keyword→category mapping from keyword_map.json."""
    map_path = Path(__file__).parent / "keyword_map.json"
    if not map_path.exists():
        raise FileNotFoundError(f"keyword_map.json not found at {map_path}")
    return json.loads(map_path.read_text(encoding="utf-8"))
