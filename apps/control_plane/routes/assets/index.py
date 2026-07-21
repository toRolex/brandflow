"""Asset indexing endpoints and background task runner."""

from __future__ import annotations

import asyncio
import sqlite3

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from apps.control_plane.index_tasks import index_task_manager
from apps.control_plane.routes.assets import helpers
from apps.control_plane.routes.assets.helpers import (
    _background_tasks,
    _run_index_task,
    _sanitize_filename,
)
from packages.pipeline_services.asset_library import AssetIndexer, AssetRepository
from packages.pipeline_services.asset_library.category_config import get_categories
from packages.pipeline_services.media_utils import _resolve_ffmpeg_path

router = APIRouter()


@router.post("/index")
async def index_assets(
    request: Request,
    async_mode: bool = Query(True),
    product: str | None = Query(None),
):
    root_dir: Path = request.app.state.root_dir
    source_dir = root_dir / "workspace" / "shared_assets" / "source"
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

    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
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
    product_value = helpers._resolve_product_name(config_reader, product or "")

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
    vision_config = helpers.resolve_vision_config(
        {}, secrets=secret_store, reader=config_reader
    )
    try:
        helpers.validate_vision_config(config_reader, secret_store)
    except helpers.VisionConfigError as e:
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
    output_base = root_dir / "workspace" / "shared_assets" / "indexed"
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
