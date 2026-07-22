"""Asset reclassification endpoints (batch and single)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.assets import helpers
from apps.control_plane.routes.assets.helpers import _reclassify_single_asset, logger
from packages.pipeline_services.asset_library import AssetRepository
from packages.pipeline_services.asset_library.vision_utils import VisionConfigError

router = APIRouter()


@router.post("/batch/reclassify")
async def batch_reclassify_assets(request: Request):
    """POST /api/assets/batch/reclassify — 批量重跑 Vision 分类。

    每个素材独立分类：部分失败不阻塞其他素材，返回每项独立状态/错误。
    """
    root_dir: Path = request.app.state.root_dir
    config_reader = request.app.state.config_reader
    secret_store = request.app.state.secret_store

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

    # 1. Vision 配置预检（一次，不重复）
    try:
        helpers.validate_vision_config(config_reader, secret_store)
    except VisionConfigError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "vision_config_invalid", "message": str(e)},
        )

    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    vision_config = helpers.resolve_vision_config(
        {}, secrets=secret_store, reader=config_reader
    )

    results: list[dict] = []
    any_found = False

    for asset_id in asset_ids:
        record = repo.query_one(asset_id)
        if not record:
            results.append(
                {
                    "asset_id": asset_id,
                    "error": "asset not found",
                }
            )
            continue

        any_found = True

        video_path = Path(record.file_path)
        if not video_path.exists():
            results.append(
                {
                    "asset_id": asset_id,
                    "error": "video file not found",
                }
            )
            continue

        try:
            result = _reclassify_single_asset(
                video_path, db_path, asset_id, vision_config
            )
            results.append(result)
        except HTTPException as e:
            detail = (
                e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
            )
            results.append(
                {
                    "asset_id": asset_id,
                    "error": detail.get("code", detail.get("message", str(e.detail))),
                }
            )
        except Exception as e:
            logger.error("[BatchReclassify] %s 未知错误: %s", asset_id, e)
            results.append(
                {
                    "asset_id": asset_id,
                    "error": str(e),
                }
            )

    if not any_found:
        raise HTTPException(
            status_code=400,
            detail="all asset_ids failed or not found",
        )

    return {"results": results}


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
        helpers.validate_vision_config(config_reader, secret_store)
    except VisionConfigError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "vision_config_invalid", "message": str(e)},
        )

    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    video_path = Path(record.file_path)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="video file not found")

    vision_config = helpers.resolve_vision_config(
        {}, secrets=secret_store, reader=config_reader
    )
    return _reclassify_single_asset(video_path, db_path, asset_id, vision_config)
