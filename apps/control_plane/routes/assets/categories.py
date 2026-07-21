"""Batch category update endpoint."""

from __future__ import annotations

import sqlite3

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.patch("/categories")
async def batch_update_categories(request: Request):
    """PATCH /api/assets/categories — 批量重分类素材（用于未映射素材归类）。

    幂等：相同请求重复执行返回相同 updated 计数。
    只更新 asset_ids 中实际存在的素材。
    不校验 category 是否在配置分类列表中。
    限制单次最多 500 个 asset_id。
    """
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    asset_ids = body.get("asset_ids")
    category = body.get("category")

    if (
        not isinstance(asset_ids, list)
        or not asset_ids
        or any(not isinstance(i, str) for i in asset_ids)
    ):
        raise HTTPException(
            status_code=400, detail="asset_ids must be a non-empty string array"
        )
    if not isinstance(category, str) or not category.strip():
        raise HTTPException(status_code=400, detail="category is required")

    # Limit to 500 per request
    if len(asset_ids) > 500:
        asset_ids = asset_ids[:500]

    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        return {"updated": 0}

    conn = sqlite3.connect(str(db_path))
    updated = 0
    for aid in asset_ids:
        cursor = conn.execute(
            "UPDATE assets SET category = ? WHERE asset_id = ?",
            (category.strip(), aid),
        )
        updated += cursor.rowcount
    conn.commit()
    conn.close()
    return {"updated": updated}
