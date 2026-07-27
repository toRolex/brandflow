from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from typing import Any

from packages.domain_core.models import JobRecord
from packages.file_store.layout import AmbiguousJobError, WorkspaceLayout
from packages.pagination import slice_indices


class DuplicateProjectNameError(ValueError):
    """Raised when a Project name is already present in the workspace."""


class FileStoreRepository:
    # Per-project file-locks for append-only JSONL files (review_events.jsonl)
    # so concurrent Jobs in the same project don't interleave or corrupt lines.
    _append_locks: dict[str, threading.Lock] = {}
    _append_locks_guard: threading.Lock = threading.Lock()
    _project_creation_lock: threading.Lock = threading.Lock()

    def __init__(self, root: Path) -> None:
        self._layout = WorkspaceLayout(root)

    @property
    def layout(self) -> WorkspaceLayout:
        """The :class:`WorkspaceLayout` seam for project-tree paths.

        Production code should reach every project-tree path through this
        layout.  Callers needing the source root for non-project paths can use
        ``repo.layout.root``.
        """
        return self._layout

    def create_project(self, project_id: str, name: str = "") -> Path:
        root = self._layout.project_dir(project_id)
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
        meta_path = self._layout.project_meta_path(project_id)
        if not meta_path.exists():
            meta = {"id": project_id, "name": name}
            self._write_json(meta_path, meta)
        return root

    def create_project_with_unique_name(self, project_id: str, name: str) -> Path:
        """Create a Project while atomically enforcing workspace name uniqueness."""
        with self._project_creation_lock:
            projects_root = self._layout.projects_dir()
            if projects_root.exists():
                for project_dir in projects_root.iterdir():
                    if not project_dir.is_dir():
                        continue
                    meta = self.load_project_meta(project_dir.name)
                    if meta.get("name", "").strip() == name:
                        raise DuplicateProjectNameError(name)
            return self.create_project(project_id, name=name)

    def load_project_meta(self, project_id: str) -> dict[str, Any]:
        path = self._layout.project_meta_path(project_id)
        if not path.exists():
            return {"id": project_id, "name": project_id}
        return json.loads(path.read_text(encoding="utf-8"))

    def save_job(self, project_id: str, record: JobRecord) -> None:
        path = self._layout.job_record_path(project_id, record.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(path, record.model_dump())

    def load_job(self, project_id: str, job_id: str) -> JobRecord:
        path = self._layout.job_record_path(project_id, job_id)
        # ponytail: control plane auto_tick and worker advance_after_report
        # both save_job concurrently; their ``os.replace`` on Windows can
        # briefly surface a torn JSON to readers. Retry once after 50ms
        # so the caller's 404 isn't permanent.
        last_exc: Exception | None = None
        for _ in range(2):
            try:
                return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (ValueError, OSError) as exc:
                last_exc = exc
                import time

                time.sleep(0.05)
        raise last_exc  # type: ignore[misc]

    def find_project_for_job(self, job_id: str) -> str | None:
        """Return the unique Project that owns *job_id*.

        A Job ID is only globally usable by routes when exactly one valid
        record owns it.  Corrupt records are skipped so a damaged historical
        file cannot hide another project's valid Job; duplicate valid records
        are reported explicitly instead of selecting an arbitrary project.
        """
        # Validate before scanning: invalid IDs must retain the layout seam's
        # InvalidWorkspacePath signal rather than being silently treated as a
        # missing Job.
        self._layout.job_record_path("job-owner-validation", job_id)

        owners: list[str] = []
        projects_root = self._layout.projects_dir()
        if not projects_root.exists():
            return None

        for project_dir in sorted(projects_root.iterdir(), key=lambda path: path.name):
            if not project_dir.is_dir():
                continue
            project_id = project_dir.name
            if not self._layout.job_record_path(project_id, job_id).exists():
                continue
            try:
                record = self.load_job(project_id, job_id)
            except (OSError, ValueError):
                continue
            if record.job_id == job_id:
                owners.append(project_id)

        if len(owners) > 1:
            raise AmbiguousJobError(owners)
        return owners[0] if owners else None

    def delete_job(self, project_id: str, job_id: str) -> bool:
        path = self._layout.job_record_path(project_id, job_id)
        if not path.exists():
            return False
        path.unlink()
        runtime_dir = self._layout.job_runtime_dir(project_id, job_id)
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)
        return True

    def append_review_event(self, project_id: str, event: dict[str, Any]) -> None:
        path = self._layout.review_events_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Serialise writes per-project so concurrent Jobs don't interleave
        # JSON lines or corrupt each other's writes.
        with self._append_locks_guard:
            lock = self._append_locks.get(project_id)
            if lock is None:
                lock = threading.Lock()
                self._append_locks[project_id] = lock
        with lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def count_jobs(self, project_id: str) -> int:
        """Count Job JSON files without deserialising any JobRecord."""
        jobs_root = self._layout.control_jobs_dir(project_id)
        if not jobs_root.exists():
            return 0
        return sum(
            1 for f in jobs_root.iterdir() if f.is_file() and f.suffix == ".json"
        )

    def _sorted_job_files(self, project_id: str) -> list[Path]:
        """Return ``*.json`` files under *project_id*'s jobs dir sorted by
        immutable Job creation order (#354).

        Historical records without ``created_at`` sort first by stable job_id.
        New records sort by their persisted creation timestamp, with job_id as
        a deterministic tiebreaker.
        """
        jobs_root = self._layout.control_jobs_dir(project_id)
        if not jobs_root.exists():
            return []
        files = [f for f in jobs_root.iterdir() if f.is_file() and f.suffix == ".json"]

        def creation_order(file: Path) -> tuple[int, str, str]:
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
                created_at = payload.get("created_at")
                if isinstance(created_at, str) and created_at:
                    return (1, created_at, file.stem)
            except (OSError, ValueError, TypeError):
                pass
            return (0, "", file.stem)

        return sorted(files, key=creation_order)

    def _build_job_summary(
        self, project_id: str, file: Path, display_index: str
    ) -> dict[str, Any]:
        """Read and parse one Job JSON file into the standard summary dict."""
        try:
            record = JobRecord.model_validate_json(file.read_text(encoding="utf-8"))
            asset_review_unresolved_count = None
            if record.phase == "asset_review":
                clips_path = self._layout.job_artifact_path(
                    project_id, record.job_id, "selected_clips.json"
                )
                try:
                    clips = json.loads(clips_path.read_text(encoding="utf-8"))
                    asset_review_unresolved_count = sum(
                        clip.get("visual_type", "unresolved") == "unresolved"
                        for clip in clips
                    )
                except (OSError, ValueError):
                    asset_review_unresolved_count = None
            return {
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
        except Exception:
            return {
                "job_id": file.stem,
                "phase": "unknown",
                "review_status": "unknown",
                "display_index": display_index,
            }

    def list_jobs(self, project_id: str) -> list[dict[str, Any]]:
        """Return all Job summaries sorted by creation order (immutable)."""
        files = self._sorted_job_files(project_id)
        results: list[dict[str, Any]] = []
        for idx, f in enumerate(files, start=1):
            display_index = f"{idx:03d}"
            results.append(self._build_job_summary(project_id, f, display_index))
        return results

    def list_jobs_paginated(
        self, project_id: str, page: int = 1, page_size: int = 50
    ) -> tuple[list[dict[str, Any]], int]:
        """Return a (items, total) pair for the requested page.

        Items are sorted by immutable Job creation order.  ``total`` is the
        pre-slice count from a single directory snapshot.
        """
        files = self._sorted_job_files(project_id)
        total = len(files)
        start, end = slice_indices(total, page, page_size)
        results: list[dict[str, Any]] = []
        for idx, f in enumerate(files[start:end], start=start + 1):
            display_index = f"{idx:03d}"
            results.append(self._build_job_summary(project_id, f, display_index))
        return results, total

    def list_assets(self, project_id: str) -> list[dict[str, Any]]:
        assets_root = self._layout.source_assets_dir(project_id)
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
        asset_path = self._layout.source_asset_path(project_id, asset_name)
        if not asset_path.exists():
            return False
        asset_path.unlink()
        return True

    def delete_project(self, project_id: str) -> bool:
        root = self._layout.project_dir(project_id)
        if not root.exists():
            return False
        shutil.rmtree(root)
        return True

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        # ponytail: unique tmp per writer — two concurrent writers (control
        # plane auto_tick + worker advance_after_report) used to share
        # ``<path>.tmp`` and clobber each other's bytes, leaving truncated
        # JSON that load_job surfaces as a 404.
        import os
        import tempfile

        fd, tmp_name = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
