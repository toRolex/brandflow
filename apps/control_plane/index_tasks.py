"""后台索引任务管理器"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import AsyncGenerator


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IndexTask:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    current_step: str = "cut"
    current_video: int = 0
    total_videos: int = 0
    logs: list[str] = field(default_factory=list)
    result: dict | None = None
    error: str | None = None
    created_at: str = ""
    completed_at: str | None = None


class IndexTaskManager:
    def __init__(self) -> None:
        self._tasks: dict[str, IndexTask] = {}
        self._log_queues: dict[str, asyncio.Queue[str]] = {}

    def create_task(self, total_videos: int) -> IndexTask:
        task_id = f"idx_{uuid.uuid4().hex[:12]}"
        task = IndexTask(
            task_id=task_id,
            total_videos=total_videos,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._tasks[task_id] = task
        self._log_queues[task_id] = asyncio.Queue()
        return task

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        stale = [
            tid
            for tid, task in list(self._tasks.items())
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
            and task.completed_at is not None
            and datetime.fromisoformat(task.completed_at) < cutoff
        ]
        for tid in stale:
            del self._tasks[tid]
            self._log_queues.pop(tid, None)

    def get_task(self, task_id: str) -> IndexTask | None:
        self._prune()
        return self._tasks.get(task_id)

    def add_log(self, task_id: str, message: str) -> None:
        if task_id in self._tasks:
            logs = self._tasks[task_id].logs
            if len(logs) > 500:
                logs.pop(0)
            logs.append(message)
            if task_id in self._log_queues:
                try:
                    self._log_queues[task_id].put_nowait(message)
                except asyncio.QueueFull:
                    pass

    async def get_log_stream(self, task_id: str) -> AsyncGenerator[str, None]:
        if task_id not in self._log_queues:
            return
        queue = self._log_queues[task_id]
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30)
                yield f"data: {message}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"


index_task_manager = IndexTaskManager()
