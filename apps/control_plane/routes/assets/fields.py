"""Asset field update endpoints (batch and single)."""

from __future__ import annotations

import shutil
import sqlite3

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.assets.helpers import _validate_category
from packages.pipeline_services.asset_library import AssetRepository

router = APIRouter()


@router.patch("/batch-fields")
async def batch_update_fields(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    asset_ids = body.get("asset_ids")
    if (
        not isinstance(asset_ids, list)
        or not asset_ids
        or any(not isinstance(i, str) or not i for i in asset_ids)
    ):
        raise HTTPException(
            status_code=400, detail="asset_ids must be a non-empty string array"
        )

    new_product = body.get("product")
    new_category = body.get("category")

    if not new_product and not new_category:
        return {"updated": 0}

    root_dir: Path = request.app.state.root_dir
    _validate_category(new_category, root_dir)

    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    indexed_dir = root_dir / "workspace" / "shared_assets" / "indexed"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    updated = 0

    for aid in asset_ids:
        row = conn.execute("SELECT * FROM assets WHERE asset_id = ?", (aid,)).fetchone()
        if not row:
            continue

        old_product = row["product"]
        old_category = row["category"]
        old_file_path = row["file_path"]

        product = new_product or old_product
        category = new_category or old_category

        new_dir = indexed_dir / product / category
        new_dir.mkdir(parents=True, exist_ok=True)

        old_file = Path(old_file_path)
        if old_file.exists():
            new_file = new_dir / old_file.name
            if old_file.parent != new_dir:
                shutil.move(str(old_file), str(new_file))
            new_file_path = str(new_file.resolve())
        else:
            new_file_path = old_file_path

        conn.execute(
            "UPDATE assets SET product = ?, category = ?, file_path = ? WHERE asset_id = ?",
            (product, category, new_file_path, aid),
        )
        updated += 1

    conn.commit()
    conn.close()
    return {"updated": updated}


@router.patch("/{asset_id}/fields")
async def patch_asset_fields(request: Request, asset_id: str):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    new_product = body.get("product")
    new_category = body.get("category")

    _validate_category(new_category, root_dir)

    if not new_product and not new_category:
        return {"updated": 0}

    product = new_product or record.product
    category = new_category or record.category

    indexed_dir = root_dir / "workspace" / "shared_assets" / "indexed"
    new_dir = indexed_dir / product / category
    new_dir.mkdir(parents=True, exist_ok=True)

    old_file = Path(record.file_path)
    if old_file.exists():
        new_file = new_dir / old_file.name
        if old_file.parent != new_dir:
            shutil.move(str(old_file), str(new_file))
        new_file_path = str(new_file.resolve())
    else:
        new_file_path = record.file_path

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "UPDATE assets SET product = ?, category = ?, file_path = ? WHERE asset_id = ?",
        (product, category, new_file_path, asset_id),
    )
    conn.commit()
    conn.close()
    return {"updated": 1}
