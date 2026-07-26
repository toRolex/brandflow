from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from packages.file_store.repository import FileStoreRepository
from packages.pagination import paginated

router = APIRouter(prefix="/api/projects", tags=["api-projects"])


class CreateProjectRequest(BaseModel):
    name: str


@router.get("")
def list_projects(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """Return paginated Project summaries sorted by stable project_id."""
    repo = FileStoreRepository(request.app.state.root_dir)
    projects_root = repo.root / "workspace" / "projects"
    if not projects_root.exists():
        return paginated([], 0, page, page_size)

    # One snapshot: collect all project ids first, then slice
    all_dirs = sorted(
        [d for d in projects_root.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )
    total = len(all_dirs)
    start = (page - 1) * page_size
    if start >= total:
        return paginated([], total, page, page_size)
    end = min(start + page_size, total)

    items: list[dict[str, object]] = []
    for prj_dir in all_dirs[start:end]:
        meta = repo.load_project_meta(prj_dir.name)
        job_count = repo.count_jobs(prj_dir.name)
        items.append(
            {
                "id": prj_dir.name,
                "name": meta.get("name", prj_dir.name),
                "status": "idle",
                "job_count": job_count,
            }
        )
    return paginated(items, total, page, page_size)


@router.post("")
def create_project(request: Request, payload: CreateProjectRequest):
    project_id = f"prj_{uuid.uuid4().hex[:12]}"
    repo = FileStoreRepository(request.app.state.root_dir)
    repo.create_project(project_id, name=payload.name)
    return {"id": project_id, "name": payload.name, "status": "idle", "job_count": 0}


@router.get("/{project_id}")
def get_project(request: Request, project_id: str):
    """Return Project metadata only (no longer embeds full jobs list)."""
    repo = FileStoreRepository(request.app.state.root_dir)
    meta = repo.load_project_meta(project_id)
    job_count = repo.count_jobs(project_id)
    return {
        "id": project_id,
        "name": meta.get("name", project_id),
        "status": "idle",
        "job_count": job_count,
    }


@router.get("/{project_id}/jobs")
def list_project_jobs(
    request: Request,
    project_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """Return paginated Job summaries for *project_id*, sorted by stable job_id."""
    repo = FileStoreRepository(request.app.state.root_dir)
    # Verify project exists
    if not (repo.root / "workspace" / "projects" / project_id).is_dir():
        raise HTTPException(status_code=404, detail="Project not found")
    items, total = repo.list_jobs_paginated(project_id, page=page, page_size=page_size)
    return paginated(items, total, page, page_size)


@router.delete("/{project_id}")
def delete_project(request: Request, project_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    if not repo.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return {"ok": True}
