"""Scene segment management API — folder listing, file upload, and file management."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile

from packages.provider_config.app_config import AppConfigManager

router = APIRouter(prefix="/api/scene", tags=["scene"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}


def _get_scene_folders(root_dir: Path) -> list[dict]:
    """Return the scene folder config entries."""
    app_config = AppConfigManager(config_dir=str(root_dir / "config"))
    scene_config = app_config.get_scene_config()
    return scene_config.get("folders", [])


def _get_scene_config(root_dir: Path) -> dict:
    """Return the full scene config."""
    app_config = AppConfigManager(config_dir=str(root_dir / "config"))
    return app_config.get_scene_config()


def _folder_exists_in_config(root_dir: Path, folder_name: str) -> bool:
    """Check if a folder name exists in scene config by its path field."""
    for entry in _get_scene_folders(root_dir):
        if entry.get("path", "") == folder_name:
            return True
    return False


def _scene_dir(root_dir: Path, folder_name: str) -> Path:
    """Return the workspace directory for a scene folder."""
    return root_dir / "workspace" / "scene" / folder_name


@router.post("/upload")
async def upload_scene_file(request: Request, folder: str, file: UploadFile):
    """Upload a video file to a scene folder.

    - ``folder`` (query param): the scene folder path name (e.g. ``brand-intro``)
    - ``file`` (multipart): the video file (mp4 / mov / avi / webm only)
    """
    root_dir: Path = request.app.state.root_dir

    # Validate folder exists in config
    if not _folder_exists_in_config(root_dir, folder):
        raise HTTPException(
            status_code=400,
            detail=f"Folder '{folder}' not found in scene configuration",
        )

    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Ensure destination directory exists
    dest_dir = _scene_dir(root_dir, folder)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Unique filename: timestamp prefix to avoid collisions
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = f"{timestamp}_{Path(file.filename).name}"
    dest_path = dest_dir / safe_name

    # Save file
    content = await file.read()
    dest_path.write_bytes(content)

    return {
        "name": safe_name,
        "path": str(dest_path),
        "folder": folder,
        "size_bytes": len(content),
    }


@router.get("/folders")
def list_scene_folders(request: Request):
    """List all configured scene folders with file counts."""
    root_dir: Path = request.app.state.root_dir
    folders = _get_scene_folders(root_dir)
    scene_config = _get_scene_config(root_dir)
    transition_duration_ms = scene_config.get("transition_duration_ms", 500)

    result: list[dict] = []
    for entry in folders:
        folder_path = entry.get("path", "")
        folder_dir = _scene_dir(root_dir, folder_path)
        file_count = 0
        if folder_dir.exists():
            file_count = sum(
                1
                for f in folder_dir.iterdir()
                if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
            )
        result.append(
            {
                "name": entry.get("name", folder_path),
                "path": folder_path,
                "file_count": file_count,
            }
        )

    return {"folders": result, "transition_duration_ms": transition_duration_ms}


@router.get("/folders/{folder_name}/files")
def list_folder_files(request: Request, folder_name: str):
    """List existing files in a scene folder."""
    root_dir: Path = request.app.state.root_dir

    if not _folder_exists_in_config(root_dir, folder_name):
        raise HTTPException(
            status_code=404,
            detail=f"Folder '{folder_name}' not found in scene configuration",
        )

    folder_dir = _scene_dir(root_dir, folder_name)

    if not folder_dir.exists():
        return {"files": []}

    files: list[dict] = []
    for f in sorted(folder_dir.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        stat = f.stat()
        files.append(
            {
                "name": f.name,
                "size_bytes": stat.st_size,
                "uploaded_at": datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).isoformat(),
            }
        )

    return {"files": files}


@router.delete("/folders/{folder_name}/files/{file_name}", status_code=204)
def delete_folder_file(request: Request, folder_name: str, file_name: str):
    """Delete a specific file from a scene folder."""
    root_dir: Path = request.app.state.root_dir

    if not _folder_exists_in_config(root_dir, folder_name):
        raise HTTPException(
            status_code=404,
            detail=f"Folder '{folder_name}' not found in scene configuration",
        )

    folder_dir = _scene_dir(root_dir, folder_name)

    if not folder_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Folder directory not found: 'scene/{folder_name}'",
        )

    file_path = folder_dir / file_name
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"File '{file_name}' not found in folder '{folder_name}'",
        )

    # Sanity check: ensure we are not deleting a parent path
    resolved = file_path.resolve()
    if resolved.parent != folder_dir.resolve():
        raise HTTPException(
            status_code=400,
            detail="Cannot delete file outside the scene folder",
        )

    file_path.unlink()
