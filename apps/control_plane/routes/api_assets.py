"""Shared asset library routes — all projects see the same global asset pool."""

from __future__ import annotations

from fastapi import APIRouter

from apps.control_plane.routes.assets import (
    categories,
    delete,
    fields,
    index,
    migrate,
    query,
    reclassify,
    source,
    status,
    thumbnails,
)

router = APIRouter(prefix="/api/assets", tags=["api-assets"])

# 注意顺序：静态路径 /batch、/batch-fields、/migrate 等必须在动态 /{asset_id} 之前挂载
router.include_router(source.router, tags=["api-assets"])
router.include_router(query.router, tags=["api-assets"])
router.include_router(index.router, tags=["api-assets"])
router.include_router(categories.router, tags=["api-assets"])
router.include_router(fields.router, tags=["api-assets"])
router.include_router(status.router, tags=["api-assets"])
router.include_router(migrate.router, tags=["api-assets"])
router.include_router(delete.router, tags=["api-assets"])
router.include_router(thumbnails.router, tags=["api-assets"])
router.include_router(reclassify.router, tags=["api-assets"])
