from __future__ import annotations

from fastapi import APIRouter

from apps.control_plane.routes.jobs import (
    content,
    cover_title,
    crud,
    export,
    metadata,
    migration,
    tts,
)

router = APIRouter(prefix="/api", tags=["api-jobs"])

# Include more specific job-level subpaths before the catch-all /jobs/{job_id}
# routes in ``crud`` to prevent dynamic path shadowing.
router.include_router(metadata.router)
router.include_router(cover_title.router)
router.include_router(export.router)
router.include_router(tts.router)
router.include_router(content.router)
router.include_router(migration.router)
router.include_router(crud.router)
