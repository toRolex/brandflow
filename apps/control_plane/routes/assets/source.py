"""Source asset endpoints (upload / list)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from apps.control_plane.routes.assets.helpers import _sanitize_filename

router = APIRouter()


@router.post("/upload")
async def upload_asset(request: Request, file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    root_dir: Path = request.app.state.root_dir
    source_dir = root_dir / "workspace" / "shared_assets" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(file.filename)
    dest = source_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)
    return {"name": safe_name, "size_bytes": len(content), "in_use": False}


@router.get("/list")
def list_source_assets(request: Request):
    root_dir: Path = request.app.state.root_dir
    source_dir = root_dir / "workspace" / "shared_assets" / "source"
    if not source_dir.exists():
        return []
    return [
        {"name": f.name, "size_bytes": f.stat().st_size, "in_use": False}
        for f in sorted(source_dir.iterdir())
        if f.is_file()
    ]
