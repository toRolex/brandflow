from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class TTSRequestLog:
    id: str
    task_id: str
    project_id: str
    timestamp: datetime
    model: str
    voice_id: str
    style_prompt: str
    text_length: int
    success: bool
    audio_duration_ms: int | None
    latency_ms: int
    error_type: str | None
    error_message: str | None
    attempt_count: int
    final_voice_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "timestamp": self.timestamp.isoformat(),
            "model": self.model,
            "voice_id": self.voice_id,
            "style_prompt": self.style_prompt,
            "text_length": self.text_length,
            "success": self.success,
            "audio_duration_ms": self.audio_duration_ms,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "attempt_count": self.attempt_count,
            "final_voice_id": self.final_voice_id,
        }


@dataclass
class TTSMetrics:
    time_range: str = "24h"
    total_requests: int = 0
    success_count: int = 0
    failure_count: int = 0
    success_rate: float = 0.0
    avg_latency_ms: int = 0
    p95_latency_ms: int = 0
    p99_latency_ms: int = 0
    avg_audio_duration_ms: int = 0
    total_audio_duration_ms: int = 0
    error_distribution: dict[str, int] = field(default_factory=dict)
    voice_distribution: dict[str, int] = field(default_factory=dict)

    def __post_init__(self):
        if self.total_requests > 0:
            self.success_rate = self.success_count / self.total_requests


class TTSMonitor:
    def __init__(self, log_dir: str = "logs/tts"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._logs: list[TTSRequestLog] = []

    def record_request(self, log: TTSRequestLog) -> None:
        self._logs.append(log)
        self._write_log_to_file(log)

    def get_logs(
        self,
        project_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[TTSRequestLog]:
        filtered = self._logs.copy()

        if project_id:
            filtered = [entry for entry in filtered if entry.project_id == project_id]

        if status == "failed":
            filtered = [entry for entry in filtered if not entry.success]
        elif status == "success":
            filtered = [entry for entry in filtered if entry.success]

        return filtered[offset:offset + limit]

    def get_metrics(
        self,
        project_id: str | None = None,
        time_range: str = "24h",
    ) -> TTSMetrics:
        logs = self._logs
        if project_id:
            logs = [entry for entry in logs if entry.project_id == project_id]

        total = len(logs)
        success = sum(1 for entry in logs if entry.success)
        failure = total - success

        latencies = [entry.latency_ms for entry in logs]
        avg_latency = sum(latencies) // len(latencies) if latencies else 0

        durations = [entry.audio_duration_ms for entry in logs if entry.audio_duration_ms]
        avg_duration = sum(durations) // len(durations) if durations else 0
        total_duration = sum(durations)

        error_dist: dict[str, int] = {}
        for log in logs:
            if log.error_type:
                error_dist[log.error_type] = error_dist.get(log.error_type, 0) + 1

        voice_dist: dict[str, int] = {}
        for log in logs:
            voice_dist[log.final_voice_id] = voice_dist.get(log.final_voice_id, 0) + 1

        return TTSMetrics(
            time_range=time_range,
            total_requests=total,
            success_count=success,
            failure_count=failure,
            success_rate=success / total if total > 0 else 0.0,
            avg_latency_ms=avg_latency,
            avg_audio_duration_ms=avg_duration,
            total_audio_duration_ms=total_duration,
            error_distribution=error_dist,
            voice_distribution=voice_dist,
        )

    def _write_log_to_file(self, log: TTSRequestLog) -> None:
        date_str = log.timestamp.strftime("%Y-%m-%d")
        log_file = self.log_dir / f"{date_str}.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log.to_dict(), ensure_ascii=False) + "\n")
