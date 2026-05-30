"""Shared asset library routes — all projects see the same global asset pool."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from packages.file_store.paths import (
    shared_asset_db_path,
    shared_assets_root,
    shared_indexed_dir,
    shared_source_dir,
)
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.asset_library import AssetIndexer, AssetRepository

router = APIRouter(prefix="/api/assets", tags=["api-assets"])


def _sanitize_filename(filename: str) -> str:
    return Path(filename).name


@router.post("/upload")
async def upload_asset(request: Request, file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    root_dir: Path = request.app.state.root_dir
    source_dir = shared_source_dir(root_dir)
    source_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(file.filename)
    dest = source_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)
    return {"name": safe_name, "size_bytes": len(content), "in_use": False}


@router.get("/list")
def list_source_assets(request: Request):
    root_dir: Path = request.app.state.root_dir
    source_dir = shared_source_dir(root_dir)
    if not source_dir.exists():
        return []
    return [
        {"name": f.name, "size_bytes": f.stat().st_size, "in_use": False}
        for f in sorted(source_dir.iterdir())
        if f.is_file()
    ]


@router.get("/indexed")
def get_indexed_assets(
    request: Request,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    root_dir: Path = request.app.state.root_dir
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        return {
            "assets": [],
            "stats": {"total_clips": 0, "available_clips": 0, "disabled_clips": 0, "source_videos": 0},
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


@router.post("/index")
def index_assets(request: Request):
    root_dir: Path = request.app.state.root_dir
    source_dir = shared_source_dir(root_dir)
    source_dir.mkdir(parents=True, exist_ok=True)

    videos = [
        f for f in sorted(source_dir.iterdir())
        if f.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}
    ]

    db_path = shared_asset_db_path(root_dir)
    indexed_sources: set[str] = set()
    total_before = 0
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT source_video FROM assets").fetchall()
        total_before = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        conn.close()
        indexed_sources = {row[0] for row in rows if row[0]}

    new_videos = [v for v in videos if str(v.resolve()) not in indexed_sources]

    if new_videos:
        repository = AssetRepository(db_path)

        from packages.provider_config.store import load_provider_config
        from packages.pipeline_services.asset_library.vision_client import resolve_vision_config

        providers = load_provider_config(root_dir)
        vision_config = resolve_vision_config(providers)

        product = os.environ.get("PRODUCT", "见手青")

        indexer = AssetIndexer(
            ffmpeg_path=os.environ.get("FFMPEG_PATH", "ffmpeg"),
            repository=repository,
            vision_config=vision_config,
            product=product,
        )
        output_base = shared_indexed_dir(root_dir)
        for video in new_videos:
            try:
                indexer._ingest_one_video(video, output_base)
            except Exception as e:
                print(f"[INDEX ERROR] {video.name}: {e}")

    total_clips = total_before
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        total_clips = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        conn.close()

    return {"indexed": len(new_videos), "skipped": len(videos) - len(new_videos), "total_clips": total_clips}


@router.patch("/batch")
async def batch_update_status(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    status = body.get("status")
    asset_ids = body.get("asset_ids")

    if status not in {"pending_review", "available", "disabled"}:
        raise HTTPException(status_code=400, detail="invalid status")
    if not isinstance(asset_ids, list) or not asset_ids or any(not isinstance(i, str) or not i for i in asset_ids):
        raise HTTPException(status_code=400, detail="asset_ids must be a non-empty string array")

    root_dir: Path = request.app.state.root_dir
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        return {"updated": 0}

    conn = sqlite3.connect(str(db_path))
    updated = 0
    for aid in asset_ids:
        cursor = conn.execute("UPDATE assets SET status = ? WHERE asset_id = ?", (status, aid))
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
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        return {"updated": 0}

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("UPDATE assets SET status = ? WHERE asset_id = ?", (status, asset_id))
    updated = cursor.rowcount
    conn.commit()
    conn.close()
    return {"updated": updated}


@router.post("/migrate")
def migrate_project_assets(request: Request):
    """Migrate all per-project assets into the shared library."""
    root_dir: Path = request.app.state.root_dir
    projects_root = root_dir / "workspace" / "projects"
    if not projects_root.exists():
        return {"migrated_projects": 0, "migrated_clips": 0, "migrated_sources": 0}

    shared_db_path = shared_asset_db_path(root_dir)
    shared_src = shared_source_dir(root_dir)
    shared_idx = shared_indexed_dir(root_dir)
    shared_src.mkdir(parents=True, exist_ok=True)
    shared_idx.mkdir(parents=True, exist_ok=True)

    # Ensure shared DB table exists
    AssetRepository(shared_db_path)

    migrated_projects = 0
    migrated_clips = 0
    migrated_sources = 0

    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir():
            continue

        # Migrate source assets
        src_dir = project_dir / "runtime" / "source_assets"
        if src_dir.exists():
            for f in src_dir.iterdir():
                if f.is_file():
                    dest = shared_src / f.name
                    if not dest.exists():
                        shutil.copy2(str(f), str(dest))
                        migrated_sources += 1

        # Migrate indexed clips DB
        old_db = project_dir / "asset_index.db"
        if old_db.exists():
            old_conn = sqlite3.connect(str(old_db))
            old_conn.row_factory = sqlite3.Row
            rows = old_conn.execute("SELECT * FROM assets").fetchall()
            old_conn.close()

            if rows:
                new_conn = sqlite3.connect(str(shared_db_path))
                for row in rows:
                    d = dict(row)
                    try:
                        new_conn.execute(
                            """INSERT OR IGNORE INTO assets
                               (asset_id, file_path, category, product, confidence, duration_seconds,
                                status, usage_count, source_video, tags, created_at, last_used_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                d["asset_id"], d["file_path"], d["category"], d["product"],
                                d["confidence"], d["duration_seconds"], d["status"],
                                d["usage_count"], d["source_video"],
                                d["tags"] if isinstance(d["tags"], str) else json.dumps(d["tags"], ensure_ascii=False),
                                d["created_at"], d["last_used_at"],
                            ),
                        )
                        migrated_clips += 1
                    except sqlite3.IntegrityError:
                        pass  # already exists
                new_conn.commit()
                new_conn.close()
                migrated_projects += 1

        # Migrate indexed clips files
        idx_dir = project_dir / "runtime" / "indexed_clips"
        if idx_dir.exists():
            for product_dir in idx_dir.iterdir():
                if not product_dir.is_dir():
                    continue
                for cat_dir in product_dir.iterdir():
                    if not cat_dir.is_dir():
                        continue
                    dest_cat = shared_idx / product_dir.name / cat_dir.name
                    dest_cat.mkdir(parents=True, exist_ok=True)
                    for clip in cat_dir.iterdir():
                        if clip.is_file():
                            dest = dest_cat / clip.name
                            if not dest.exists():
                                shutil.copy2(str(clip), str(dest))

    return {
        "migrated_projects": migrated_projects,
        "migrated_clips": migrated_clips,
        "migrated_sources": migrated_sources,
    }
