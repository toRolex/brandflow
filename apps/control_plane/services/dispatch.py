from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import _compute_transition


class Dispatcher:
    def __init__(self, repo: FileStoreRepository) -> None:
        self._repo = repo
        self.current_attempts: dict[str, dict[str, str]] = {}

    def poll(self, worker_id: str) -> dict[str, object]:
        projects_root = self._repo.root / "workspace" / "projects"
        if not projects_root.exists():
            return {"command": "idle", "next_poll_after_seconds": 5}

        project_dirs = sorted(
            [d for d in projects_root.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )

        for project_dir in project_dirs:
            project_id = project_dir.name
            job_infos = self._repo.list_jobs(project_id)
            for job_info in job_infos:
                job_id = job_info.get("job_id")
                if not job_id:
                    continue
                try:
                    record = self._repo.load_job(project_id, job_id)
                except Exception:
                    continue

                action = _compute_transition(record, ())
                if action.run_handler and action.handler_phase:
                    task_id = f"task-{job_id}"
                    attempt_id = f"attempt-{uuid4().hex[:8]}"
                    lease_id = f"lease-{uuid4().hex[:8]}"
                    lease_expires_at = (
                        datetime.now(timezone.utc) + timedelta(minutes=3)
                    ).isoformat()
                    self.current_attempts[task_id] = {
                        "project_id": project_id,
                        "job_id": job_id,
                        "attempt_id": attempt_id,
                        "lease_id": lease_id,
                        "worker_id": worker_id,
                    }
                    return {
                        "command": "run_task",
                        "mode": record.mode,
                        "handler_phase": action.handler_phase,
                        "project_id": project_id,
                        "job_id": job_id,
                        "product": record.product,
                        "brand": record.brand,
                        "task_id": task_id,
                        "task_type": "run_phase",
                        "lease_id": lease_id,
                        "attempt_id": attempt_id,
                        "lease_expires_at": lease_expires_at,
                        "input_bundle_url": f"/workers/tasks/{task_id}/input-bundle",
                        "report_url": f"/workers/tasks/{task_id}/report",
                        "heartbeat_url": f"/workers/tasks/{task_id}/heartbeat",
                        "expected_outputs": ["script", "audio", "subtitles", "final_video"],
                        "runtime_limits": {"max_seconds": 1800},
                        "manual_script": record.manual_script,
                        "uploaded_audio_path": record.uploaded_audio_path,
                        "audio_source": record.audio_source,
                        "language": record.language,
                        "cover_title": record.cover_title.model_dump(),
                        "music_track_path": record.music_track_path,
                        "music_volume": record.music_volume,
                    }

        return {"command": "idle", "next_poll_after_seconds": 5}

    def accept_report(self, task_id: str, attempt_id: str, lease_id: str) -> bool:
        current = self.current_attempts.get(task_id)
        if current is None:
            return False
        return current["attempt_id"] == attempt_id and current["lease_id"] == lease_id
