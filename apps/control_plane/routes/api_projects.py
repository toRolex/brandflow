from __future__ import annotations

import os
import sqlite3
import tempfile
import uuid

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.asset_library import AssetIndexer, AssetRepository

router = APIRouter(prefix="/api/projects", tags=["api-projects"])


class CreateProjectRequest(BaseModel):
    name: str


@router.get("")
def list_projects(request: Request):
    repo = FileStoreRepository(request.app.state.root_dir)
    projects_root = repo.root / "workspace" / "projects"
    projects: list[dict[str, object]] = []
    if projects_root.exists():
        for prj_dir in sorted(projects_root.iterdir()):
            if prj_dir.is_dir():
                meta = repo.load_project_meta(prj_dir.name)
                jobs = repo.list_jobs(prj_dir.name)
                projects.append({
                    "id": prj_dir.name,
                    "name": meta.get("name", prj_dir.name),
                    "status": "idle",
                    "job_count": len(jobs),
                })
    return projects


@router.post("")
def create_project(request: Request, payload: CreateProjectRequest):
    project_id = f"prj_{uuid.uuid4().hex[:12]}"
    repo = FileStoreRepository(request.app.state.root_dir)
    repo.create_project(project_id, name=payload.name)
    return {"id": project_id, "name": payload.name, "status": "idle", "job_count": 0}


@router.get("/{project_id}")
def get_project(request: Request, project_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    meta = repo.load_project_meta(project_id)
    jobs = repo.list_jobs(project_id)
    return {
        "id": project_id,
        "name": meta.get("name", project_id),
        "status": "idle",
        "job_count": len(jobs),
        "jobs": jobs,
    }


def _sanitize_filename(filename: str) -> str:
    return Path(filename).name


@router.post("/{project_id}/upload")
async def upload_asset(request: Request, project_id: str, file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    repo = FileStoreRepository(request.app.state.root_dir)
    assets_dir = repo.create_project(project_id, name=project_id) / "runtime" / "source_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(file.filename)
    dest = assets_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)
    return {"name": safe_name, "size_bytes": len(content), "in_use": False}


@router.get("/{project_id}/assets")
def list_assets(request: Request, project_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    return repo.list_assets(project_id)


def _project_dir(root_dir: Path, project_id: str) -> Path:
    return root_dir / "workspace" / "projects" / project_id


def _asset_db_path(project_dir: Path) -> Path:
    return project_dir / "asset_index.db"


@router.get("/{project_id}/assets/indexed")
def get_indexed_assets(request: Request, project_id: str):
    project_dir = _project_dir(request.app.state.root_dir, project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="project not found")

    db_path = _asset_db_path(project_dir)
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
    rows = conn.execute("SELECT * FROM assets ORDER BY created_at DESC").fetchall()
    total_clips = len(rows)
    available_clips = sum(1 for row in rows if row["status"] == "available")
    disabled_clips = sum(1 for row in rows if row["status"] == "disabled")
    source_videos = len({row["source_video"] for row in rows if row["source_video"]})
    conn.close()

    return {
        "assets": [dict(row) for row in rows],
        "stats": {
            "total_clips": total_clips,
            "available_clips": available_clips,
            "disabled_clips": disabled_clips,
            "source_videos": source_videos,
        },
    }


@router.post("/{project_id}/assets/index")
def index_assets(request: Request, project_id: str):
    project_dir = _project_dir(request.app.state.root_dir, project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="project not found")

    source_dir = project_dir / "runtime" / "source_assets"
    source_dir.mkdir(parents=True, exist_ok=True)

    videos = [
        file_path for file_path in sorted(source_dir.iterdir())
        if file_path.suffix.lower() in {".mp4", ".mov", ".avi", ".mkv"}
    ]

    db_path = _asset_db_path(project_dir)
    indexed_sources: set[str] = set()
    total_before = 0
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute("SELECT source_video FROM assets").fetchall()
        total_before = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        conn.close()
        indexed_sources = {row[0] for row in rows if row[0]}

    new_videos = [video for video in videos if str(video.resolve()) not in indexed_sources]

    if new_videos:
        repository = AssetRepository(db_path)
        indexer = AssetIndexer(
            ffmpeg_path=os.environ.get("FFMPEG_PATH", "ffmpeg"),
            repository=repository,
            product=os.environ.get("PRODUCT", "见手青"),
        )
        with tempfile.TemporaryDirectory(prefix="asset_index_staging_") as temp_dir:
            staging_dir = Path(temp_dir)
            for video in new_videos:
                (staging_dir / video.name).write_bytes(video.read_bytes())
            indexer.ingest_videos(staging_dir, project_dir / "runtime" / "indexed_clips")

    total_clips = total_before
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        total_clips = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        conn.close()

    return {
        "indexed": len(new_videos),
        "skipped": len(videos) - len(new_videos),
        "total_clips": total_clips,
    }


@router.patch("/{project_id}/assets/{asset_id}")
async def patch_asset_status(request: Request, project_id: str, asset_id: str):
    body = await request.json()
    status = body.get("status")
    asset_ids = body.get("asset_ids")

    if status not in {"pending_review", "available", "disabled"}:
        raise HTTPException(status_code=400, detail="invalid status")

    target_ids = asset_ids if asset_id == "batch" else [asset_id]
    if asset_id == "batch" and not target_ids:
        raise HTTPException(status_code=400, detail="asset_ids required for batch")

    project_dir = _project_dir(request.app.state.root_dir, project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="project not found")

    db_path = _asset_db_path(project_dir)
    if not db_path.exists():
        return {"updated": 0}

    conn = sqlite3.connect(str(db_path))
    updated = 0
    for target_id in target_ids:
        cursor = conn.execute(
            "UPDATE assets SET status = ? WHERE asset_id = ?",
            (status, target_id),
        )
        updated += cursor.rowcount
    conn.commit()
    conn.close()

    return {"updated": updated}


@router.delete("/{project_id}/assets/{asset_name}")
def delete_asset(request: Request, project_id: str, asset_name: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    safe_name = _sanitize_filename(asset_name)
    if safe_name != asset_name:
        raise HTTPException(status_code=400, detail="invalid asset name")
    ok = repo.delete_asset(project_id, safe_name)
    if not ok:
        raise HTTPException(status_code=404, detail="asset not found")
    return {"status": "deleted"}
