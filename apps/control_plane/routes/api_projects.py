from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request
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
    print(f"[API-DELETE] project_id={project_id}", flush=True)
    repo = FileStoreRepository(request.app.state.root_dir)
    if not repo.delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    print(f"[API-DELETE] project_id={project_id} DONE", flush=True)
    return {"ok": True}
