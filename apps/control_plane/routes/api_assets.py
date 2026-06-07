"""Shared asset library routes — all projects see the same global asset pool."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
import uuid

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from apps.control_plane.index_tasks import index_task_manager, TaskStatus

from packages.file_store.paths import (
    shared_asset_db_path,
    shared_assets_root,
    shared_indexed_dir,
    shared_source_dir,
)
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.asset_library import AssetIndexer, AssetRepository
from packages.pipeline_services.asset_library.thumbnail import ThumbnailGenerator, _resolve_tool_path, _get_default

router = APIRouter(prefix="/api/assets", tags=["api-assets"])

# 存储后台任务引用，防止被垃圾回收
_background_tasks: set[asyncio.Task] = set()


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
async def index_assets(request: Request, async_mode: bool = Query(True)):
    root_dir: Path = request.app.state.root_dir
    source_dir = shared_source_dir(root_dir)
    source_dir.mkdir(parents=True, exist_ok=True)

    videos = [
        f for f in sorted(source_dir.iterdir())
        if f.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}
    ]

    db_path = shared_asset_db_path(root_dir)
    indexed_sources: set[str] = set()
    if db_path.exists():
        repository_for_check = AssetRepository(db_path)
        indexed_sources = repository_for_check.get_indexed_source_paths()

    new_videos = [v for v in videos if str(v.resolve()) not in indexed_sources]

    if not new_videos:
        total_clips = 0
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            total_clips = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            conn.close()
        return {"indexed": 0, "skipped": len(videos), "total_clips": total_clips}

    if async_mode:
        task = index_task_manager.create_task(len(new_videos))
        print(f"[INDEX] 创建异步任务: {task.task_id}, 待处理 {len(new_videos)} 个视频")
        bg_task = asyncio.create_task(_run_index_task(task.task_id, root_dir, new_videos, db_path))
        _background_tasks.add(bg_task)
        bg_task.add_done_callback(_background_tasks.discard)
        return {"task_id": task.task_id, "total_videos": len(new_videos)}

    repository = AssetRepository(db_path)
    from packages.provider_config.store import load_provider_config
    from packages.pipeline_services.asset_library.vision_client import resolve_vision_config

    providers = load_provider_config(root_dir)
    vision_config = resolve_vision_config(providers)
    product = os.environ.get("PRODUCT", "荔枝菌")
    ffmpeg_path = _resolve_tool_path(_get_default("FFMPEG_PATH", "ffmpeg"))
    indexer = AssetIndexer(
        ffmpeg_path=ffmpeg_path,
        repository=repository,
        vision_config=vision_config,
        product=product,
    )
    output_base = shared_indexed_dir(root_dir)
    for video in new_videos:
        try:
            indexer._ingest_one_video(video, output_base)
            repository.mark_source_indexed(str(video.resolve()))
        except Exception as e:
            print(f"[INDEX ERROR] {video.name}: {e}")

    total_clips = 0
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        total_clips = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        conn.close()

    return {"indexed": len(new_videos), "skipped": len(videos) - len(new_videos), "total_clips": total_clips}


async def _run_index_task(task_id: str, root_dir: Path, videos: list[Path], db_path: Path):
    task = index_task_manager.get_task(task_id)
    if not task:
        return

    task.status = TaskStatus.RUNNING
    index_task_manager.add_log(task_id, f"开始处理 {len(videos)} 个视频")
    print(f"[INDEX] 任务开始: {task_id}, 共 {len(videos)} 个视频")

    try:
        repository = AssetRepository(db_path)
        from packages.provider_config.store import load_provider_config
        from packages.pipeline_services.asset_library.vision_client import resolve_vision_config

        providers = load_provider_config(root_dir)
        vision_config = resolve_vision_config(providers)
        product = os.environ.get("PRODUCT", "荔枝菌")
        ffmpeg_path = _resolve_tool_path(_get_default("FFMPEG_PATH", "ffmpeg"))
        indexer = AssetIndexer(
            ffmpeg_path=ffmpeg_path,
            repository=repository,
            vision_config=vision_config,
            product=product,
        )
        output_base = shared_indexed_dir(root_dir)

        for i, video in enumerate(videos):
            task.current_video = i + 1
            task.progress = (i / len(videos)) * 100
            task.current_step = "cut"
            index_task_manager.add_log(task_id, f"[{i+1}/{len(videos)}] 处理视频: {video.name}")

            def log_callback(msg: str) -> None:
                index_task_manager.add_log(task_id, msg)

            await asyncio.get_event_loop().run_in_executor(
                None, lambda v=video: indexer._ingest_one_video(v, output_base, log_callback=log_callback)
            )
            repository.mark_source_indexed(str(video.resolve()))
            task.current_step = "classify" if i < len(videos) - 1 else "done"

        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.current_step = "done"
        task.completed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        index_task_manager.add_log(task_id, "索引完成")
        print(f"[INDEX] 任务完成: {task_id}, 共处理 {len(videos)} 个视频")
    except Exception as e:
        task.status = TaskStatus.FAILED
        task.error = str(e)
        index_task_manager.add_log(task_id, f"错误: {e}")
        print(f"[INDEX ERROR] 任务失败: {task_id}, 错误: {type(e).__name__}: {e}")


@router.get("/index/{task_id}/status")
def get_index_status(task_id: str):
    task = index_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "progress": task.progress,
        "current_step": task.current_step,
        "current_video": task.current_video,
        "total_videos": task.total_videos,
        "error": task.error,
    }


@router.get("/index/{task_id}/logs")
async def get_index_logs(task_id: str):
    task = index_task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return StreamingResponse(
        index_task_manager.get_log_stream(task_id),
        media_type="text/event-stream",
    )


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


@router.patch("/batch-fields")
async def batch_update_fields(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    asset_ids = body.get("asset_ids")
    if not isinstance(asset_ids, list) or not asset_ids or any(not isinstance(i, str) or not i for i in asset_ids):
        raise HTTPException(status_code=400, detail="asset_ids must be a non-empty string array")

    new_product = body.get("product")
    new_category = body.get("category")

    if not new_product and not new_category:
        return {"updated": 0}

    if new_category:
        from packages.pipeline_services.asset_library.models import Category
        try:
            Category(new_category)
        except ValueError:
            valid = [c.value for c in Category]
            raise HTTPException(status_code=400, detail=f"invalid category, must be one of: {valid}")

    root_dir: Path = request.app.state.root_dir
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    indexed_dir = shared_indexed_dir(root_dir)
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
            (product, category, new_file_path, aid)
        )
        updated += 1

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


@router.patch("/{asset_id}/fields")
async def patch_asset_fields(request: Request, asset_id: str):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    root_dir: Path = request.app.state.root_dir
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    new_product = body.get("product")
    new_category = body.get("category")

    if not new_product and not new_category:
        return {"updated": 0}

    if new_category:
        from packages.pipeline_services.asset_library.models import Category
        try:
            Category(new_category)
        except ValueError:
            valid = [c.value for c in Category]
            raise HTTPException(status_code=400, detail=f"invalid category, must be one of: {valid}")

    product = new_product or record.product
    category = new_category or record.category.value

    indexed_dir = shared_indexed_dir(root_dir)
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
        (product, category, new_file_path, asset_id)
    )
    conn.commit()
    conn.close()
    return {"updated": 1}


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


@router.delete("/batch")
async def batch_delete_assets(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    asset_ids = body.get("asset_ids")
    if not isinstance(asset_ids, list) or not asset_ids or any(not isinstance(i, str) or not i for i in asset_ids):
        raise HTTPException(status_code=400, detail="asset_ids must be a non-empty string array")

    root_dir: Path = request.app.state.root_dir
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        return {"deleted": 0}

    repository = AssetRepository(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    deleted = 0
    files_deleted = 0
    thumbnail_dir = shared_assets_root(root_dir) / "thumbnails"
    source_videos_to_check: set[str] = set()

    for aid in asset_ids:
        row = conn.execute("SELECT file_path, source_video FROM assets WHERE asset_id = ?", (aid,)).fetchone()
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


@router.get("/{asset_id}/thumbnail")
async def get_asset_thumbnail(request: Request, asset_id: str):
    root_dir: Path = request.app.state.root_dir
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    thumbnail_dir = shared_assets_root(root_dir) / "thumbnails"
    thumbnail_path = thumbnail_dir / f"{asset_id}.jpg"

    if not thumbnail_path.exists():
        video_path = Path(record.file_path)
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="video file not found")

        generator = ThumbnailGenerator()
        success = generator.generate(video_path, thumbnail_path)
        if not success:
            raise HTTPException(status_code=500, detail="failed to generate thumbnail")

    return FileResponse(thumbnail_path, media_type="image/jpeg")


@router.delete("/{asset_id}")
async def delete_asset(request: Request, asset_id: str):
    root_dir: Path = request.app.state.root_dir
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    file_path = Path(record.file_path)
    if file_path.exists():
        file_path.unlink()

    thumbnail_path = shared_assets_root(root_dir) / "thumbnails" / f"{asset_id}.jpg"
    if thumbnail_path.exists():
        thumbnail_path.unlink()

    conn = sqlite3.connect(str(db_path))
    conn.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
    conn.commit()
    conn.close()

    return {"status": "deleted"}
