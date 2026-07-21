"""Asset thumbnail endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from apps.control_plane.routes.assets import helpers
from packages.pipeline_services.asset_library import AssetRepository

router = APIRouter()


@router.get("/{asset_id}/thumbnail")
async def get_asset_thumbnail(request: Request, asset_id: str):
    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="asset db not found")

    repo = AssetRepository(db_path)
    record = repo.query_one(asset_id)
    if not record:
        raise HTTPException(status_code=404, detail="asset not found")

    thumbnail_dir = root_dir / "workspace" / "shared_assets" / "thumbnails"
    thumbnail_path = thumbnail_dir / f"{asset_id}.jpg"

    if not thumbnail_path.exists():
        video_path = Path(record.file_path)
        if not video_path.exists():
            raise HTTPException(status_code=404, detail="video file not found")

        generator = helpers.ThumbnailGenerator()
        success = generator.generate(video_path, thumbnail_path)
        if not success:
            raise HTTPException(status_code=500, detail="failed to generate thumbnail")

    return FileResponse(thumbnail_path, media_type="image/jpeg")
