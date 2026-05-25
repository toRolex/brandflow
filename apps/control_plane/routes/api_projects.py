from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from apps.control_plane.routes.projects import _scan_projects
from packages.file_store.repository import FileStoreRepository

router = APIRouter(prefix="/api/projects", tags=["api-projects"])


class CreateProjectRequest(BaseModel):
    name: str


@router.get("")
def list_projects():
    return _scan_projects()


@router.post("")
def create_project(request: Request, payload: CreateProjectRequest):
    project_id = f"prj_{uuid.uuid4().hex[:12]}"
    repo = FileStoreRepository(request.app.state.root_dir)
    repo.create_project(project_id)
    return {"id": project_id, "name": payload.name, "status": "idle", "job_count": 0}


@router.get("/{project_id}")
def get_project(request: Request, project_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    jobs = repo.list_jobs(project_id)
    return {
        "id": project_id,
        "name": project_id,
        "status": "idle",
        "job_count": len(jobs),
        "jobs": jobs,
    }


@router.post("/{project_id}/upload")
async def upload_asset(request: Request, project_id: str, file: UploadFile):
    repo = FileStoreRepository(request.app.state.root_dir)
    assets_dir = repo.create_project(project_id) / "runtime" / "source_assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    dest = assets_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)
    return {"name": file.filename, "size_bytes": len(content), "in_use": False}


@router.get("/{project_id}/assets")
def list_assets(request: Request, project_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    return repo.list_assets(project_id)


@router.delete("/{project_id}/assets/{asset_name}")
def delete_asset(request: Request, project_id: str, asset_name: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    ok = repo.delete_asset(project_id, asset_name)
    if not ok:
        raise HTTPException(status_code=404, detail="asset not found")
    return {"status": "deleted"}
