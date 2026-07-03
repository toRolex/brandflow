from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PollRequest(BaseModel):
    worker_id: str
    worker_version: str
    capabilities: list[str] = Field(default_factory=list)
    current_tasks: list[str] = Field(default_factory=list)
    free_slots: int = 1


class PollCommandIdle(BaseModel):
    command: Literal["idle"]
    next_poll_after_seconds: int


class PollCommandRunTask(BaseModel):
    command: Literal["run_task"]
    handler_phase: str
    project_id: str
    job_id: str
    task_id: str
    task_type: str
    lease_id: str
    attempt_id: str
    lease_expires_at: str
    input_bundle_url: str
    report_url: str
    heartbeat_url: str
    expected_outputs: list[str]
    runtime_limits: dict[str, int]


class WorkerReport(BaseModel):
    worker_id: str
    project_id: str
    job_id: str
    task_id: str
    attempt_id: str
    lease_id: str
    status: Literal["succeeded", "failed", "blocked", "cancelled"]
    started_at: str
    finished_at: str
    artifact_manifest: dict = Field(default_factory=dict)
    metrics: dict = Field(default_factory=dict)
    logs_summary: str = ""
    error: dict = Field(default_factory=dict)
