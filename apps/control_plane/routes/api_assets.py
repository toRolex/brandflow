"""Shared asset library routes — all projects see the same global asset pool."""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sqlite3
import tempfile

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile

from packages.pipeline_services.asset_library.category_config import get_categories
from packages.pipeline_services.asset_library.vision_client import (
    VisionClient,
    resolve_vision_config,
)
from fastapi.responses import FileResponse, StreamingResponse
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore

from apps.control_plane.index_tasks import index_task_manager, TaskStatus

from packages.file_store.paths import (
    shared_asset_db_path,
    shared_assets_root,
    shared_indexed_dir,
    shared_source_dir,
)
from packages.pipeline_services.asset_library import AssetIndexer, AssetRepository
from packages.pipeline_services.asset_library.thumbnail import ThumbnailGenerator
from packages.pipeline_services.asset_library.vision_utils import (
    VisionConfigError,
    validate_vision_config,
)
from packages.pipeline_services.media_utils import _resolve_ffmpeg_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/assets", tags=["api-assets"])

# 存储后台任务引用，防止被垃圾回收
_background_tasks: set[asyncio.Task] = set()


def _sanitize_filename(filename: str) -> str:
    return Path(filename).name


def _resolve_product_name(config_reader, explicit_product: str = "") -> str:
    """Resolve product name with fallback chain.

    Priority: explicit_product > active product name > default_name > id.
    """
    if explicit_product:
        return explicit_product
    active_id = config_reader.active_product_id
    if active_id:
        config = config_reader.get_product_config(product_id=active_id)
    else:
        config = config_reader.get_product_config()
    name = config.get("name", "")
    if name:
        return name
    default = config.get("default_name", "")
    if default:
        return default
    return config.get("id", "")


def _get_valid_category_names(root_dir: Path) -> set[str]:
    """Return the set of category names that are currently valid.

    Uses get_categories with ConfigReader so it respects product-config
    -> instance-config -> default-food-categories priority chain.
    """
    from packages.provider_config.config_reader import ConfigReader

    reader = ConfigReader(config_dir=str(root_dir / "config"))
    active_id = reader.active_product_id
    return {c.name for c in get_categories(reader, product_id=active_id or None)}


def _validate_category(category: str | None, root_dir: Path) -> None:
    """Raise 400 if *category* is not None and not in the allowed set."""
    if category is None:
        return
    allowed = _get_valid_category_names(root_dir)
    if category not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"无效分类: '{category}'，当前允许的分类: {', '.join(sorted(allowed))}",
        )


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
    product: str | None = Query(default=None),
):
    root_dir: Path = request.app.state.root_dir
    db_path = shared_asset_db_path(root_dir)
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


@router.post("/index")
async def index_assets(
    request: Request,
    async_mode: bool = Query(True),
    product: str | None = Query(None),
):
    root_dir: Path = request.app.state.root_dir
    source_dir = shared_source_dir(root_dir)
    source_dir.mkdir(parents=True, exist_ok=True)

    # 读取可选的 source_paths（Issue #144），只索引指定文件
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass
    source_paths: list[str] | None = (
        body.get("source_paths") if isinstance(body, dict) else None
    )

    if source_paths is not None:
        videos = []
        for name in source_paths:
            safe = _sanitize_filename(name)
            f = source_dir / safe
            if f.exists() and f.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}:
                videos.append(f)
        videos.sort()
    else:
        videos = [
            f
            for f in sorted(source_dir.iterdir())
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

    config_reader = request.app.state.config_reader
    product_value = _resolve_product_name(config_reader, product or "")

    if async_mode:
        task = index_task_manager.create_task(len(new_videos))
        print(f"[INDEX] 创建异步任务: {task.task_id}, 待处理 {len(new_videos)} 个视频")
        secret_store = request.app.state.secret_store
        active_id = config_reader.active_product_id
        category_names = [
            c.name for c in get_categories(config_reader, product_id=active_id or None)
        ]
        bg_task = asyncio.create_task(
            _run_index_task(
                task.task_id,
                root_dir,
                new_videos,
                db_path,
                product_value,
                config_reader,
                secret_store,
                category_names,
            )
        )
        _background_tasks.add(bg_task)
        bg_task.add_done_callback(_background_tasks.discard)
        return {"task_id": task.task_id, "total_videos": len(new_videos)}

    repository = AssetRepository(db_path)
    secret_store = request.app.state.secret_store
    active_id = config_reader.active_product_id
    vision_config = resolve_vision_config(
        {}, secrets=secret_store, reader=config_reader
    )
    # 仅当 Vision 被显式配置（有 api_key）时才校验完整性
    if vision_config.get("api_key"):
        try:
            validate_vision_config(config_reader, secret_store)
        except VisionConfigError as e:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "vision_config_invalid",
                    "message": str(e),
                },
            )
    category_names = [
        c.name for c in get_categories(config_reader, product_id=active_id or None)
    ]
    ffmpeg_path = _resolve_ffmpeg_path()
    indexer = AssetIndexer(
        ffmpeg_path=ffmpeg_path,
        repository=repository,
        vision_config=vision_config,
        product=product_value,
        category_names=category_names,
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

    return {
        "indexed": len(new_videos),
        "skipped": len(videos) - len(new_videos),
        "total_clips": total_clips,
    }


async def _run_index_task(
    task_id: str,
    root_dir: Path,
    videos: list[Path],
    db_path: Path,
    product: str,
    config_reader: "ConfigReader | None" = None,
    secret_store: "SecretStore | None" = None,
    category_names: list[str] | None = None,
):
    task = index_task_manager.get_task(task_id)
    if not task:
        return

    task.status = TaskStatus.RUNNING
    index_task_manager.add_log(task_id, f"开始处理 {len(videos)} 个视频")
    print(f"[INDEX] 任务开始: {task_id}, 共 {len(videos)} 个视频, product={product}")

    try:
        repository = AssetRepository(db_path)

        if config_reader is not None:
            vision_config = resolve_vision_config(
                {}, secrets=secret_store, reader=config_reader
            )
        else:
            from packages.provider_config.config_reader import ConfigReader

            vision_config = resolve_vision_config(
                {},
                secrets=secret_store,
                reader=ConfigReader(config_dir=str(root_dir / "config")),
            )

        # 仅当 Vision 被显式配置（有 api_key）时才校验完整性
        if vision_config.get("api_key"):
            validate_vision_config(config_reader, secret_store)

        ffmpeg_path = _resolve_ffmpeg_path()
        indexer = AssetIndexer(
            ffmpeg_path=ffmpeg_path,
            repository=repository,
            vision_config=vision_config,
            product=product,
            category_names=category_names,
        )
        output_base = shared_indexed_dir(root_dir)

        for i, video in enumerate(videos):
            task.current_video = i + 1
            task.progress = (i / len(videos)) * 100
            task.current_step = "cut"
            index_task_manager.add_log(
                task_id, f"[{i + 1}/{len(videos)}] 处理视频: {video.name}"
            )

            def log_callback(msg: str) -> None:
                index_task_manager.add_log(task_id, msg)

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda v=video: indexer._ingest_one_video(
                    v, output_base, log_callback=log_callback
                ),
            )
            repository.mark_source_indexed(str(video.resolve()))
            task.current_step = "classify" if i < len(videos) - 1 else "done"

        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.current_step = "done"
        task.completed_at = (
            __import__("datetime")
            .datetime.now(__import__("datetime").timezone.utc)
            .isoformat()
        )
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
    db_path = shared_asset_db_path(root_dir)
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
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        return {"updated": 0}

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
            (product, category, new_file_path, aid),
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
    cursor = conn.execute(
        "UPDATE assets SET status = ? WHERE asset_id = ?", (status, asset_id)
    )
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

    _validate_category(new_category, root_dir)

    if not new_product and not new_category:
        return {"updated": 0}

    product = new_product or record.product
    category = new_category or record.category

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
        (product, category, new_file_path, asset_id),
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
        return {
            "migrated_projects": 0,
            "migrated_clips": 0,
            "migrated_sources": 0,
            "migrated_video_source_records": 0,
            "conflicts": 0,
            "skipped_ids": [],
            "verification": {"old_count": 0, "new_count": 0, "diff": 0},
        }

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
    migrated_video_source_records = 0
    conflicts = 0
    skipped_ids: list[str] = []

    # Count old DB rows before migration (for post-verification comparison)
    old_count = 0
    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir():
            continue
        old_db = project_dir / "asset_index.db"
        if old_db.exists():
            try:
                old_conn = sqlite3.connect(str(old_db))
                old_count += old_conn.execute("SELECT COUNT(*) FROM assets").fetchone()[
                    0
                ]
                old_conn.close()
            except sqlite3.Error:
                pass  # silently skip corrupt DBs

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

            # Migrate source_videos table from old DB
            old_source_rows = old_conn.execute(
                "SELECT source_path, indexed_at FROM source_videos"
            ).fetchall()
            if old_source_rows:
                new_conn = sqlite3.connect(str(shared_db_path))
                for source_path, indexed_at in old_source_rows:
                    new_conn.execute(
                        "INSERT OR IGNORE INTO source_videos (source_path, indexed_at) VALUES (?, ?)",
                        (source_path, indexed_at),
                    )
                new_conn.commit()
                new_conn.close()
                migrated_video_source_records += len(old_source_rows)

            old_conn.close()

            if rows:
                new_conn = sqlite3.connect(str(shared_db_path))
                for row in rows:
                    d = dict(row)
                    # Rewrite file_path from per-project dir to shared_assets/indexed
                    old_fp = Path(d["file_path"])
                    d["file_path"] = str(
                        shared_idx / d["product"] / d["category"] / old_fp.name
                    )
                    cursor = new_conn.execute(
                        """INSERT OR IGNORE INTO assets
                           (asset_id, file_path, category, product, confidence, duration_seconds,
                            status, usage_count, source_video, tags, created_at, last_used_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            d["asset_id"],
                            d["file_path"],
                            d["category"],
                            d["product"],
                            d["confidence"],
                            d["duration_seconds"],
                            d["status"],
                            d["usage_count"],
                            d["source_video"],
                            d["tags"]
                            if isinstance(d["tags"], str)
                            else json.dumps(d["tags"], ensure_ascii=False),
                            d["created_at"],
                            d["last_used_at"],
                        ),
                    )
                    if cursor.rowcount > 0:
                        migrated_clips += 1
                    else:
                        conflicts += 1
                        skipped_ids.append(d["asset_id"])
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

    # Backfill any source_video references from assets that were added
    # via INSERT OR IGNORE conflicts
    repo = AssetRepository(shared_db_path)
    backfilled = repo.backfill_source_videos()
    migrated_video_source_records += backfilled

    # Post-verification: count rows in shared DB after migration
    new_count = 0
    shared_db = Path(shared_db_path)
    if shared_db.exists():
        try:
            verify_conn = sqlite3.connect(str(shared_db))
            new_count = verify_conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            verify_conn.close()
        except sqlite3.Error:
            pass

    return {
        "migrated_projects": migrated_projects,
        "migrated_clips": migrated_clips,
        "migrated_sources": migrated_sources,
        "migrated_video_source_records": migrated_video_source_records,
        "conflicts": conflicts,
        "skipped_ids": skipped_ids,
        "verification": {
            "old_count": old_count,
            "new_count": new_count,
            "diff": new_count - old_count,
        },
    }


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


@router.post("/{asset_id}/reclassify")
async def reclassify_asset(request: Request, asset_id: str):
    """POST /api/assets/{asset_id}/reclassify — 单素材重跑 Vision 分类。

    Vision 配置预检 → 提取帧 → Vision 分类 → 更新素材。
    """
    root_dir: Path = request.app.state.root_dir
    config_reader = request.app.state.config_reader
    secret_store = request.app.state.secret_store

    # 1. Vision 配置预检
    try:
        validate_vision_config(config_reader, secret_store)
    except VisionConfigError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "vision_config_invalid", "message": str(e)},
        )

    # 2. 获取素材
    db_path = shared_asset_db_path(root_dir)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    video_path = Path(record.file_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="video file not found")

    # 3. 提取帧并调用 Vision 分类
    temp_dir = Path(tempfile.mkdtemp(prefix="reclassify_"))
    try:
        frame_path = temp_dir / "frame.jpg"
        generator = ThumbnailGenerator()
        if not generator.generate(video_path, frame_path):
            raise HTTPException(status_code=500, detail="failed to extract video frame")

        vision_config = resolve_vision_config(
            {}, secrets=secret_store, reader=config_reader
        )
        client = VisionClient(
            api_key=vision_config.get("api_key", ""),
            endpoint=vision_config.get("endpoint", ""),
            model=vision_config.get("model", ""),
            provider=vision_config.get("provider", ""),
        )
        result = client.classify_frame(frame_path)
        category = result.get("category", "产品特写")
        confidence = float(result.get("confidence", 0.0))

        if confidence == 0:
            raise HTTPException(
                status_code=422,
                detail={"code": "zero_confidence", "message": "Vision 返回置信度为 0"},
            )

        # 4. 更新素材
        status = "available"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "UPDATE assets SET category = ?, confidence = ?, status = ? WHERE asset_id = ?",
            (category, confidence, status, asset_id),
        )
        conn.commit()
        conn.close()

        logger.info(
            "[Reclassify] %s → %s (confidence: %.2f)", asset_id, category, confidence
        )

        return {
            "asset_id": asset_id,
            "category": category,
            "confidence": confidence,
            "status": status,
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
