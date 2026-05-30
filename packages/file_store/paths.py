from __future__ import annotations

from pathlib import Path


def workspace_root(root: Path) -> Path:
    return root / "workspace"


def projects_root(root: Path) -> Path:
    return workspace_root(root) / "projects"


def shared_assets_root(root: Path) -> Path:
    return workspace_root(root) / "shared_assets"


def shared_asset_db_path(root: Path) -> Path:
    return shared_assets_root(root) / "asset_index.db"


def shared_source_dir(root: Path) -> Path:
    return shared_assets_root(root) / "source"


def shared_indexed_dir(root: Path) -> Path:
    return shared_assets_root(root) / "indexed"


def project_root(root: Path, project_id: str) -> Path:
    return projects_root(root) / project_id


def job_manifest_path(root: Path, project_id: str, job_id: str) -> Path:
    return project_root(root, project_id) / "runtime" / "jobs" / job_id / "job_manifest.json"
