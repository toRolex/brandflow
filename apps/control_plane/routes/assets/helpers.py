"""Shared helpers for asset library routes."""

from __future__ import annotations

import asyncio
import logging
import requests
import shutil
import sqlite3
import tempfile

from pathlib import Path

from fastapi import HTTPException

from apps.control_plane.index_tasks import index_task_manager, TaskStatus
from packages.pipeline_services.asset_library import (
    AssetIndexer,
    AssetRecord,
    AssetRepository,
)
from packages.pipeline_services.asset_library.category_config import get_categories
from packages.pipeline_services.asset_library.thumbnail import ThumbnailGenerator
from packages.pipeline_services.asset_library.vision_client import (
    VisionClient,
    resolve_vision_config,
)
from packages.pipeline_services.asset_library.vision_utils import (
    VisionConfigError,
    validate_vision_config,
)
from packages.pipeline_services.media_utils import _resolve_ffmpeg_path
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore

logger = logging.getLogger(__name__)

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


def _needs_reclassify(record: AssetRecord, root_dir: Path) -> bool:
    """Return True if this asset needs reclassification before enable."""
    if record.status == "classification_failed":
        return True
    if record.confidence <= 0:
        return True
    valid_categories = _get_valid_category_names(root_dir)
    if record.category not in valid_categories:
        return True
    return False


def _reclassify_asset_internal(
    config_reader: ConfigReader,
    secret_store: SecretStore,
    record: AssetRecord,
) -> tuple[str, float]:
    """Shared reclassify logic: validate config, extract frame, call Vision.

    Returns (category, confidence) on success.
    Raises HTTPException on failure (vision_config_invalid, vision_key_invalid, zero_confidence).
    Does NOT update the DB — caller's responsibility.
    """
    # 1. Vision config pre-check
    try:
        validate_vision_config(config_reader, secret_store)
    except VisionConfigError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "vision_config_invalid", "message": str(e)},
        )

    video_path = Path(record.file_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="video file not found")

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
        try:
            result = client.classify_frame(frame_path)
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, "status_code", 0)
            if status_code in (401, 403):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "vision_key_invalid",
                        "message": "Vision API key 无效或鉴权失败",
                    },
                ) from e
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "vision_request_failed",
                    "message": f"Vision 请求失败: {e}",
                },
            ) from e

        category = result.get("category", "产品特写")
        confidence = float(result.get("confidence", 0.0))

        if confidence == 0:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "zero_confidence",
                    "message": "Vision 返回置信度为 0",
                },
            )

        return category, confidence
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


async def _run_index_task(
    task_id: str,
    root_dir: Path,
    videos: list[Path],
    db_path: Path,
    product: str,
    config_reader: ConfigReader | None = None,
    secret_store: SecretStore | None = None,
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
            vision_config = resolve_vision_config(
                {},
                secrets=secret_store,
                reader=ConfigReader(config_dir=str(root_dir / "config")),
            )

        # 索引前必须校验 Vision 配置完整性
        assert config_reader is not None, "ConfigReader required"
        assert secret_store is not None, "SecretStore required"
        try:
            validate_vision_config(config_reader, secret_store)
        except VisionConfigError as e:
            raise RuntimeError(f"Vision 配置无效: {e}")

        ffmpeg_path = _resolve_ffmpeg_path()
        indexer = AssetIndexer(
            ffmpeg_path=ffmpeg_path,
            repository=repository,
            vision_config=vision_config,
            product=product,
            category_names=category_names,
        )
        output_base = root_dir / "workspace" / "shared_assets" / "indexed"

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


def _reclassify_single_asset(
    video_path: Path,
    db_path: Path,
    asset_id: str,
    vision_config: dict,
) -> dict:
    """提取帧 → Vision 分类 → 更新 DB，返回结果字典。

    共享给单素材和批量端点使用。调用方负责素材存在性和配置预检。
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="reclassify_"))
    try:
        frame_path = temp_dir / "frame.jpg"
        generator = ThumbnailGenerator()
        if not generator.generate(video_path, frame_path):
            raise HTTPException(status_code=500, detail="failed to extract video frame")

        client = VisionClient(
            api_key=vision_config.get("api_key", ""),
            endpoint=vision_config.get("endpoint", ""),
            model=vision_config.get("model", ""),
            provider=vision_config.get("provider", ""),
        )
        try:
            result = client.classify_frame(frame_path)
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, "status_code", 0)
            if status_code in (401, 403):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "vision_key_invalid",
                        "message": "Vision API key 无效或鉴权失败",
                    },
                ) from e
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "vision_request_failed",
                    "message": f"Vision 请求失败: {e}",
                },
            ) from e

        category = result.get("category", "产品特写")
        confidence = float(result.get("confidence", 0.0))

        if confidence == 0:
            raise HTTPException(
                status_code=422,
                detail={"code": "zero_confidence", "message": "Vision 返回置信度为 0"},
            )

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
