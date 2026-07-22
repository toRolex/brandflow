"""Asset deletion endpoints (batch and single)."""

from __future__ import annotations

import sqlite3

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from packages.pipeline_services.asset_library import AssetRepository

router = APIRouter()


@router.delete("/batch")
async def batch_delete_assets(request: Request):
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

    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        return {"deleted": 0}

    repository = AssetRepository(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    deleted = 0
    files_deleted = 0
    thumbnail_dir = root_dir / "workspace" / "shared_assets" / "thumbnails"
    source_videos_to_check: set[str] = set()

    for aid in asset_ids:
        row = conn.execute(
            "SELECT file_path, source_video FROM assets WHERE asset_id = ?", (aid,)
        ).fetchone()
        if row:
            file_path = Path(row["file_path"])
            source_video = row["source_video"]
            if source_video:
                source_videos_to_check.add(source_video)

            if file_path.exists():
                try:
                    file_path.unlink()
                    files_deleted += 1
                except OSError:
                    pass

            thumb_path = thumbnail_dir / f"{aid}.jpg"
            if thumb_path.exists():
                try:
                    thumb_path.unlink()
                except OSError:
                    pass

            cursor = conn.execute("DELETE FROM assets WHERE asset_id = ?", (aid,))
            deleted += cursor.rowcount

    conn.commit()
    conn.close()

    # 检查是否还有其他资产引用同一个源视频，如果没有则删除 source_videos 记录
    for source_path in source_videos_to_check:
        remaining = repository.count_by_source(source_path)
        if remaining == 0:
            repository.remove_source_record(source_path)

    return {"deleted": deleted, "files_deleted": files_deleted}


@router.delete("/{asset_id}")
async def delete_asset(request: Request, asset_id: str):
    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    file_path = Path(record.file_path)
    if file_path.exists():
        file_path.unlink()

    thumbnail_path = (
        root_dir / "workspace" / "shared_assets" / "thumbnails" / f"{asset_id}.jpg"
    )
    if thumbnail_path.exists():
        thumbnail_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
    conn.commit()
    conn.close()

    return {"status": "deleted"}
