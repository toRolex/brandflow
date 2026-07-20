"""Durable background export task for a job's export bundle (#180).

Wraps :func:`build_export_bundle` in a persistent task whose state survives
restart. Tasks are keyed by the Final Timeline fingerprint so unchanged renders
reuse the cached ZIP, rerenders mark stale, and interrupted work is requeued.
ZIP publication is atomic — a partial package is never downloadable.
"""

from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

from packages.pipeline_services.export_service import build_export_bundle
from packages.pipeline_services.export_validation import validate_export_zip

TERMINAL_STATES = frozenset({"ready", "failed", "stale"})
BUILD_PROGRESS_START = 10
BUILD_PROGRESS_END = 85
BUILD_PROGRESS_RANGE = BUILD_PROGRESS_END - BUILD_PROGRESS_START
VALIDATED_PROGRESS = 90


class ExportTaskService:
    """Manages the single durable export task for one job."""

    def __init__(
        self,
        job_id: str,
        job_dir: Path,
        workspace_dir: Path,
        project_dir: Path,
        export_dir: Path,
        *,
        get_scene_config: Callable[[], dict[str, Any]] | None = None,
        validate_bundle: Callable[[Path], list[str]] | None = None,
    ) -> None:
        self.job_id = job_id
        self.job_dir = job_dir
        self.workspace_dir = workspace_dir
        self.project_dir = project_dir
        self.export_dir = export_dir
        self.get_scene_config = get_scene_config
        self.validate_bundle = validate_bundle or (
            lambda path: validate_export_zip(path, job_id=self.job_id)
        )
        self._task_path = export_dir / f"{job_id}.export_task.json"

    # -- public API ---------------------------------------------------------

    def create_or_reuse(self, fingerprint: str) -> dict[str, Any]:
        """Return the existing valid task or create a fresh queued one.

        A ``ready`` task is reused only when its fingerprint matches and its ZIP
        still validates; otherwise it (and any stale/invalid output) is rebuilt.
        """
        existing = self._load()
        if (
            existing
            and existing["status"] == "ready"
            and existing["fingerprint"] == fingerprint
        ):
            if self._zip_valid(Path(existing["zip_path"])):
                return existing
            # Corrupt output — delete and rebuild.
            self._delete_zip(existing)

        if (
            existing
            and existing["status"] in ("queued", "running")
            and existing["fingerprint"] == fingerprint
        ):
            return existing

        # Anything else (stale, failed, mismatched fingerprint, corrupt) → fresh task.
        if existing:
            self._delete_zip(existing)
        task = {
            "task_id": f"{self.job_id}-{uuid.uuid4().hex[:8]}",
            "job_id": self.job_id,
            "status": "queued",
            "fingerprint": fingerprint,
            "progress": 0,
            "zip_path": str(self.export_dir / f"export_{self.job_id}.zip"),
            "error": None,
        }
        self._save(task)
        return task

    def get(self, task_id: str) -> dict[str, Any] | None:
        task = self._load()
        if task and task["task_id"] == task_id:
            return task
        return None

    def run(
        self,
        task_id: str,
        *,
        build_fn: Callable[..., Path] | None = None,
    ) -> dict[str, Any]:
        """Build the bundle synchronously and publish atomically.

        The ZIP is written under a temporary name, validated, then renamed into
        place — a build or validation failure leaves no downloadable partial ZIP.
        """
        task = self.get(task_id)
        if task is None:
            raise KeyError(f"unknown export task {task_id}")
        if build_fn is None:
            build_fn = build_export_bundle

        task["status"] = "running"
        task["progress"] = BUILD_PROGRESS_START
        self._save(task)

        final_zip = Path(task["zip_path"])
        # Build into a sibling tmp dir, validate, then atomically publish.
        staging_dir = self.export_dir / f".staging_{self.job_id}"
        try:
            staging_dir.mkdir(parents=True, exist_ok=True)

            def report_build_progress(percent: int) -> None:
                mapped = BUILD_PROGRESS_START + round(
                    percent / 100 * BUILD_PROGRESS_RANGE
                )
                task["progress"] = min(
                    BUILD_PROGRESS_END,
                    max(BUILD_PROGRESS_START, mapped),
                )
                self._save(task)

            build_fn(
                job_dir=self.job_dir,
                workspace_dir=self.workspace_dir,
                project_dir=self.project_dir,
                export_dir=staging_dir,
                get_scene_config=self.get_scene_config,
                progress_callback=report_build_progress,
            )
            staged = staging_dir / final_zip.name
            if not staged.exists():
                raise RuntimeError("export bundle was not produced")
            if not self._zip_valid(staged):
                raise RuntimeError("export bundle failed structural ZIP validation")

            # Content-level validation (#255) runs before atomic publication.
            content_errors = self.validate_bundle(staged)
            if content_errors:
                raise RuntimeError(
                    "export bundle failed content validation: "
                    + "; ".join(content_errors)
                )
            task["progress"] = VALIDATED_PROGRESS
            self._save(task)
            self.export_dir.mkdir(parents=True, exist_ok=True)
            staged.replace(final_zip)  # atomic publish — no partial ZIP visible
            task["status"] = "ready"
            task["progress"] = 100
            task["error"] = None
        except Exception as exc:  # noqa: BLE001 — any failure must not leak partial zip
            if final_zip.exists():
                final_zip.unlink()
            task["status"] = "failed"
            task["progress"] = 0
            task["error"] = str(exc)
        finally:
            if staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
        self._save(task)
        return task

    def mark_stale(self) -> None:
        """Mark the current task stale (rerender) and remove its ZIP."""
        task = self._load()
        if not task or task["status"] == "stale":
            return
        self._delete_zip(task)
        task["status"] = "stale"
        task["progress"] = 0
        self._save(task)

    def recover_interrupted(self) -> dict[str, Any] | None:
        """Requeue a task left in ``running`` after a restart."""
        task = self._load()
        if task and task["status"] == "running":
            task["status"] = "queued"
            task["progress"] = 0
            self._save(task)
        return task

    # -- internals ----------------------------------------------------------

    def _set_status(self, task_id: str, status: str) -> None:
        task = self.get(task_id)
        if task:
            task["status"] = status
            self._save(task)

    def _delete_zip(self, task: dict[str, Any]) -> None:
        zip_path = Path(task.get("zip_path", ""))
        if zip_path.exists():
            zip_path.unlink()

    @staticmethod
    def _zip_valid(zip_path: Path) -> bool:
        if not zip_path.exists():
            return False
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                return zf.testzip() is None
        except zipfile.BadZipFile:
            return False

    def _load(self) -> dict[str, Any] | None:
        if not self._task_path.exists():
            return None
        return json.loads(self._task_path.read_text(encoding="utf-8"))

    def _save(self, task: dict[str, Any]) -> None:
        self._task_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._task_path.with_suffix(self._task_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(task, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(self._task_path)
