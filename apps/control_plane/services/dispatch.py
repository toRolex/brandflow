from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import uuid4


@dataclass
class QueuedTask:
    project_id: str
    job_id: str
    task_id: str
    task_type: str = "run_phase"
    manual_script: str = ""
    uploaded_audio_path: str = ""
    language: str = "mandarin"
    cover_title: dict[str, object] = field(default_factory=dict)


class Dispatcher:
    def __init__(self) -> None:
        self.queue: list[QueuedTask] = []
        self.current_attempts: dict[str, dict[str, str]] = {}

    def enqueue_demo_job(
        self,
        project_id: str,
        job_id: str,
        manual_script: str = "",
        uploaded_audio_path: str = "",
        language: str = "mandarin",
        cover_title: dict[str, object] | None = None,
    ) -> None:
        self.queue.append(
            QueuedTask(
                project_id=project_id,
                job_id=job_id,
                task_id=f"task-{job_id}",
                manual_script=manual_script,
                uploaded_audio_path=uploaded_audio_path,
                language=language,
                cover_title=cover_title or {},
            )
        )

    def poll(self, worker_id: str) -> dict[str, object]:
        if not self.queue:
            return {"command": "idle", "next_poll_after_seconds": 5}

        task = self.queue.pop(0)
        attempt_id = f"attempt-{uuid4().hex[:8]}"
        lease_id = f"lease-{uuid4().hex[:8]}"
        lease_expires_at = (
            datetime.now(timezone.utc) + timedelta(minutes=3)
        ).isoformat()
        self.current_attempts[task.task_id] = {
            "project_id": task.project_id,
            "job_id": task.job_id,
            "attempt_id": attempt_id,
            "lease_id": lease_id,
            "worker_id": worker_id,
        }
        return {
            "command": "run_task",
            "project_id": task.project_id,
            "job_id": task.job_id,
            "task_id": task.task_id,
            "task_type": task.task_type,
            "lease_id": lease_id,
            "attempt_id": attempt_id,
            "lease_expires_at": lease_expires_at,
            "input_bundle_url": f"/workers/tasks/{task.task_id}/input-bundle",
            "report_url": f"/workers/tasks/{task.task_id}/report",
            "heartbeat_url": f"/workers/tasks/{task.task_id}/heartbeat",
            "expected_outputs": ["script", "audio", "subtitles", "final_video"],
            "runtime_limits": {"max_seconds": 1800},
            "manual_script": task.manual_script,
            "uploaded_audio_path": task.uploaded_audio_path,
            "language": task.language,
            "cover_title": task.cover_title,
        }

    def accept_report(self, task_id: str, attempt_id: str, lease_id: str) -> bool:
        current = self.current_attempts.get(task_id)
        if current is None:
            return False
        return (
            current["attempt_id"] == attempt_id
            and current["lease_id"] == lease_id
        )
