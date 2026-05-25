from __future__ import annotations

import uuid

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from packages.file_store.repository import FileStoreRepository

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
    assets_dir = repo.create_project(project_id) / "runtime" / "source_assets"
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
