"""Asset status endpoints (batch and single)."""

from __future__ import annotations

import sqlite3

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.assets.helpers import (
    _get_valid_category_names,
    _needs_reclassify,
    _reclassify_asset_internal,
)
from packages.pipeline_services.asset_library import AssetRepository

router = APIRouter()


@router.patch("/batch")
async def batch_update_status(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    status = body.get("status")
    asset_ids = body.get("asset_ids")

    if status not in {"pending_review", "available", "disabled"}:
        raise HTTPException(status_code=400, detail="invalid status")
    if (
        not isinstance(asset_ids, list)
        or not asset_ids
        or any(not isinstance(i, str) or not i for i in asset_ids)
    ):
        raise HTTPException(
            status_code=400, detail="asset_ids must be a non-empty string array"
        )

    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        return {"updated": 0}

    if status != "available":
        # Simple batch update for non-available statuses
        conn = sqlite3.connect(str(db_path))
        updated = 0
        for aid in asset_ids:
            cursor = conn.execute(
                "UPDATE assets SET status = ? WHERE asset_id = ?", (status, aid)
            )
            updated += cursor.rowcount
        conn.commit()
        conn.close()
        return {"updated": updated}

    # status == "available": check each asset, auto-reclassify if needed
    config_reader = request.app.state.config_reader
    secret_store = request.app.state.secret_store

    repo = AssetRepository(db_path)

    # First pass: check all assets
    updates: list[tuple[str, str, float]] = []
    for aid in asset_ids:
        record = repo.query_one(aid)
        if not record:
            continue

        if _needs_reclassify(record, root_dir):
            category, confidence = _reclassify_asset_internal(
                config_reader, secret_store, record
            )
            # Validate result category against active list
            valid_categories = _get_valid_category_names(root_dir)
            if category not in valid_categories:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "unknown_category",
                        "message": f"Vision 返回的分类 '{category}' 不在有效分类列表中",
                    },
                )
            updates.append((aid, category, confidence))
        else:
            updates.append((aid, record.category, record.confidence))

    # Second pass: apply all updates
    conn = sqlite3.connect(str(db_path))
    updated = 0
    for aid, category, confidence in updates:
        cursor = conn.execute(
            "UPDATE assets SET status = ?, category = ?, confidence = ? WHERE asset_id = ?",
            ("available", category, confidence, aid),
        )
        updated += cursor.rowcount
    conn.commit()
    conn.close()
    return {"updated": updated}


@router.patch("/{asset_id}")
async def patch_asset_status(request: Request, asset_id: str):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    status = body.get("status")
    if status not in {"pending_review", "available", "disabled"}:
        raise HTTPException(status_code=400, detail="invalid status")

    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        return {"updated": 0}

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    # Auto-reclassify when enabling on a failing / low-confidence / invalid-category asset
    if status == "available" and _needs_reclassify(record, root_dir):
        config_reader = request.app.state.config_reader
        secret_store = request.app.state.secret_store

        category, confidence = _reclassify_asset_internal(
            config_reader, secret_store, record
        )

        # Validate result category against active list
        valid_categories = _get_valid_category_names(root_dir)
        if category not in valid_categories:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "unknown_category",
                    "message": f"Vision 返回的分类 '{category}' 不在有效分类列表中",
                },
            )

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE assets SET status = ?, category = ?, confidence = ? WHERE asset_id = ?",
            ("available", category, confidence, asset_id),
        )
        conn.commit()
        conn.close()
        return {"updated": 1}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute(
        "UPDATE assets SET status = ? WHERE asset_id = ?", (status, asset_id)
    )
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return {"updated": updated}
