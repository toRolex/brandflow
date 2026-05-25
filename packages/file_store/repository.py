from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.domain_core.models import JobRecord
from packages.file_store.paths import project_root


class FileStoreRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    def create_project(self, project_id: str) -> Path:
        root = project_root(self.root, project_id)
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
        return root

    def save_job(self, project_id: str, record: JobRecord) -> None:
        path = project_root(self.root, project_id) / "control" / "jobs" / f"{record.job_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(path, record.model_dump())

    def load_job(self, project_id: str, job_id: str) -> JobRecord:
        path = project_root(self.root, project_id) / "control" / "jobs" / f"{job_id}.json"
        return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def append_review_event(self, project_id: str, event: dict[str, Any]) -> None:
        path = project_root(self.root, project_id) / "reviews" / "review_events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def list_jobs(self, project_id: str) -> list[dict[str, Any]]:
        jobs_root = project_root(self.root, project_id) / "control" / "jobs"
        if not jobs_root.exists():
            return []
        results: list[dict[str, Any]] = []
        for f in sorted(jobs_root.iterdir()):
            if f.is_file() and f.suffix == ".json":
                try:
                    record = JobRecord.model_validate_json(f.read_text(encoding="utf-8"))
                    results.append({
                        "job_id": record.job_id,
                        "phase": record.phase,
                        "review_status": record.review_status,
                    })
                except Exception:
                    results.append({"job_id": f.stem, "phase": "unknown", "review_status": "unknown"})
        return results

    def list_assets(self, project_id: str) -> list[dict[str, Any]]:
        assets_root = project_root(self.root, project_id) / "runtime" / "source_assets"
        if not assets_root.exists():
            return []
        results: list[dict[str, Any]] = []
        for f in sorted(assets_root.iterdir()):
            if f.is_file():
                results.append({
                    "name": f.name,
                    "size_bytes": f.stat().st_size,
                    "in_use": False,
                })
        return results

    def delete_asset(self, project_id: str, asset_name: str) -> bool:
        asset_path = project_root(self.root, project_id) / "runtime" / "source_assets" / asset_name
        if not asset_path.exists():
            return False
        asset_path.unlink()
        return True

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(path)
