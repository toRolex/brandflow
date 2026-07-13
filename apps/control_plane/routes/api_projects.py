from __future__ import annotations

import json
import sqlite3
import uuid

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.asset_library import AssetIndexer, AssetRepository
from packages.pipeline_services.asset_library.category_config import get_categories
from packages.pipeline_services.asset_library.vision_client import resolve_vision_config
from packages.pipeline_services.media_utils import _resolve_ffmpeg_path

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
                projects.append(
                    {
                        "id": prj_dir.name,
                        "name": meta.get("name", prj_dir.name),
                        "status": "idle",
                        "job_count": len(jobs),
                    }
                )
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


@router.delete("/{project_id}")
def delete_project(request: Request, project_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    if not repo.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}


def _sanitize_filename(filename: str) -> str:
    return Path(filename).name


# DEPRECATED: Per-project asset management. Use global /api/assets endpoints instead.
@router.post("/{project_id}/upload")
async def upload_asset(request: Request, project_id: str, file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    repo = FileStoreRepository(request.app.state.root_dir)
    assets_dir = (
        repo.create_project(project_id, name=project_id) / "runtime" / "source_assets"
    )
    assets_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(file.filename)
    dest = assets_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)
    return {"name": safe_name, "size_bytes": len(content), "in_use": False}


# DEPRECATED: Per-project asset management. Use global /api/assets endpoints instead.
@router.get("/{project_id}/assets")
def list_assets(request: Request, project_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    return repo.list_assets(project_id)


def _project_dir(root_dir: Path, project_id: str) -> Path:
    return root_dir / "workspace" / "projects" / project_id


def _asset_db_path(project_dir: Path) -> Path:
    return project_dir / "asset_index.db"


# DEPRECATED: Per-project asset management. Use global /api/assets endpoints instead.
@router.get("/{project_id}/assets/indexed")
def get_indexed_assets(
    request: Request,
    project_id: str,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    product: str | None = Query(default=None),  # DEPRECATED: 全局端点 /api/assets/indexed 已支持
):
    """DEPRECATED — 请使用全局端点 GET /api/assets/indexed。保留仅用于兼容旧项目。"""
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

    # Build query with optional filters (parameterized to prevent SQL injection)
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


# DEPRECATED: Per-project asset management. Use global /api/assets endpoints instead.
@router.post("/{project_id}/assets/index")
def index_assets(request: Request, project_id: str):
    project_dir = _project_dir(request.app.state.root_dir, project_id)
    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="project not found")

    source_dir = project_dir / "runtime" / "source_assets"
    source_dir.mkdir(parents=True, exist_ok=True)

    videos = [
        file_path
        for file_path in sorted(source_dir.iterdir())
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

    new_videos = [
        video for video in videos if str(video.resolve()) not in indexed_sources
    ]

    if new_videos:
        repository = AssetRepository(db_path)

        from packages.provider_config.config_reader import ConfigReader

        reader = ConfigReader(config_dir=str(request.app.state.root_dir / "config"))
        secret_store = request.app.state.secret_store
        active_id = reader.active_product_id
        vision_config = resolve_vision_config({}, secrets=secret_store, reader=reader)
        category_names = [
            c.name for c in get_categories(reader, product_id=active_id or None)
        ]

        repo = FileStoreRepository(request.app.state.root_dir)
        meta = repo.load_project_meta(project_id)
        product = meta.get("product", "")
        if not product:
            config = reader.get_product_config()
            product = (
                config.get("name") or config.get("default_name") or config.get("id", "")
            )

        indexer = AssetIndexer(
            ffmpeg_path=_resolve_ffmpeg_path(),
            repository=repository,
            vision_config=vision_config,
            product=product,
            category_names=category_names,
        )
        output_base = project_dir / "runtime" / "indexed_clips"
        succeeded = 0
        for video in new_videos:
            try:
                indexer._ingest_one_video(video, output_base)
                succeeded += 1
            except Exception as e:
                print(f"[INDEX ERROR] {video.name}: {e}")

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


# DEPRECATED: Per-project asset management. Use global /api/assets endpoints instead.
@router.patch("/{project_id}/assets/{asset_id}")
async def patch_asset_status(request: Request, project_id: str, asset_id: str):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be object")

    status = body.get("status")
    asset_ids = body.get("asset_ids")

    if status not in {"pending_review", "available", "disabled"}:
        raise HTTPException(status_code=400, detail="invalid status")

    if asset_id == "batch":
        if (
            not isinstance(asset_ids, list)
            or not asset_ids
            or any(not isinstance(item, str) or not item for item in asset_ids)
        ):
            raise HTTPException(
                status_code=400, detail="asset_ids must be a non-empty string array"
            )
        target_ids = asset_ids
    else:
        target_ids = [asset_id]

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


# DEPRECATED: Per-project asset management. Use global /api/assets endpoints instead.
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
