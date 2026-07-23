from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from packages.domain_core.models import JobRecord


class FileStoreRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create_project(self, project_id: str, name: str = "") -> Path:
        root = self.root / "workspace" / "projects" / project_id
        for relative in (
            "control/jobs",
            "control/batches",
            "reviews",
            "reports",
            "runtime/jobs",
            "runtime/source_assets",
            "runtime/schedule/exports",
            "logs",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        meta_path = root / "project_meta.json"
        if not meta_path.exists():
            meta = {"id": project_id, "name": name}
            self._write_json(meta_path, meta)
        return root

    def load_project_meta(self, project_id: str) -> dict[str, Any]:
        path = self.root / "workspace" / "projects" / project_id / "project_meta.json"
        if not path.exists():
            return {"id": project_id, "name": project_id}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_job(self, project_id: str, record: JobRecord) -> None:
        path = (
            self.root
            / "workspace"
            / "projects"
            / project_id
            / "control"
            / "jobs"
            / f"{record.job_id}.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(path, record.model_dump())

    def load_job(self, project_id: str, job_id: str) -> JobRecord:
        path = (
            self.root
            / "workspace"
            / "projects"
            / project_id
            / "control"
            / "jobs"
            / f"{job_id}.json"
        )
        return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def delete_job(self, project_id: str, job_id: str) -> bool:
        path = (
            self.root
            / "workspace"
            / "projects"
            / project_id
            / "control"
            / "jobs"
            / f"{job_id}.json"
        )
        if not path.exists():
            return False
        path.unlink()
        runtime_dir = (
            self.root
            / "workspace"
            / "projects"
            / project_id
            / "runtime"
            / "jobs"
            / job_id
        )
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
        return True

    def append_review_event(self, project_id: str, event: dict[str, Any]) -> None:
        path = (
            self.root
            / "workspace"
            / "projects"
            / project_id
            / "reviews"
            / "review_events.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def list_jobs(self, project_id: str) -> list[dict[str, Any]]:
        jobs_root = (
            self.root / "workspace" / "projects" / project_id / "control" / "jobs"
        )
        if not jobs_root.exists():
            return []
        results: list[dict[str, Any]] = []
        files = sorted(
            [f for f in jobs_root.iterdir() if f.is_file() and f.suffix == ".json"],
            key=lambda f: f.stat().st_mtime,
        )
        for idx, f in enumerate(files, start=1):
            display_index = f"{idx:03d}"
            try:
                record = JobRecord.model_validate_json(f.read_text(encoding="utf-8"))
                asset_review_unresolved_count = None
                if record.phase == "asset_review":
                    clips_path = (
                        self.root
                        / "workspace"
                        / "projects"
                        / project_id
                        / "runtime"
                        / "jobs"
                        / record.job_id
                        / "selected_clips.json"
                    )
                    try:
                        clips = json.loads(clips_path.read_text(encoding="utf-8"))
                        asset_review_unresolved_count = sum(
                            clip.get("visual_type", "unresolved") == "unresolved"
                            for clip in clips
                        )
                    except (OSError, ValueError):
                        asset_review_unresolved_count = None
                results.append(
                    {
                        "job_id": record.job_id,
                        "product": record.product,
                        "phase": record.phase,
                        "review_status": record.review_status,
                        "artifacts": [a.model_dump() for a in record.artifacts],
                        "display_index": display_index,
                        "name": record.name,
                        "skip_subtitle": record.skip_subtitle,
                        "auto_approve": record.auto_approve,
                        "asset_review_unresolved_count": asset_review_unresolved_count,
                    }
                )
            except Exception:
                results.append(
                    {
                        "job_id": f.stem,
                        "phase": "unknown",
                        "review_status": "unknown",
                        "display_index": display_index,
                    }
                )
        return results

    def list_assets(self, project_id: str) -> list[dict[str, Any]]:
        assets_root = (
            self.root
            / "workspace"
            / "projects"
            / project_id
            / "runtime"
            / "source_assets"
        )
        if not assets_root.exists():
            return []
        results: list[dict[str, Any]] = []
        for f in sorted(assets_root.iterdir()):
            if f.is_file():
                results.append(
                    {
                        "name": f.name,
                        "size_bytes": f.stat().st_size,
                        "in_use": False,
                    }
                )
        return results

    def delete_asset(self, project_id: str, asset_name: str) -> bool:
        asset_path = (
            self.root
            / "workspace"
            / "projects"
            / project_id
            / "runtime"
            / "source_assets"
            / asset_name
        )
        if not asset_path.exists():
            return False
        asset_path.unlink()
        return True

    def delete_project(self, project_id: str) -> bool:
        root = self.root / "workspace" / "projects" / project_id
        if not root.exists():
            return False
        shutil.rmtree(root)
        return True

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(path)
