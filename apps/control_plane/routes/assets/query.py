"""Indexed asset query endpoint."""

from __future__ import annotations

import json
import sqlite3

from pathlib import Path

from fastapi import APIRouter, Query, Request

router = APIRouter()


@router.get("/indexed")
def get_indexed_assets(
    request: Request,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    product: str | None = Query(default=None),
):
    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        return {
            "assets": [],
            "stats": {
                "total_clips": 0,
                "available_clips": 0,
                "disabled_clips": 0,
                "source_videos": 0,
            },
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    base_query = "SELECT * FROM assets"
    conditions: list[str] = []
    params: list[str] = []
    if category:
        conditions.append("category = ?")
        params.append(category)
    if q:
        conditions.append("(file_path LIKE ? OR source_video LIKE ? OR tags LIKE ?)")
        like_q = f"%{q}%"
        params.extend([like_q, like_q, like_q])
    if product:
        conditions.append("product = ?")
        params.append(product)

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY created_at DESC"

    rows = conn.execute(base_query, params).fetchall()
    total_clips = len(rows)
    available_clips = sum(1 for row in rows if row["status"] == "available")
    disabled_clips = sum(1 for row in rows if row["status"] == "disabled")
    source_videos = len({row["source_video"] for row in rows if row["source_video"]})
    conn.close()

    assets = []
    for row in rows:
        d = dict(row)
        raw_tags = d.get("tags")
        if isinstance(raw_tags, str):
            try:
                d["tags"] = json.loads(raw_tags)
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
        assets.append(d)

    return {
        "assets": assets,
        "stats": {
            "total_clips": total_clips,
            "available_clips": available_clips,
            "disabled_clips": disabled_clips,
            "source_videos": source_videos,
        },
    }
