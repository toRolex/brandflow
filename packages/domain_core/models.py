from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Phase = Literal[
    "queued",
    "script_generating",
    "script_review",
    "tts_generating",
    "tts_review",
    "subtitle_generating",
    "asset_retrieving",
    "video_rendering",
    "final_review",
    "completed",
    "failed",
    "cancelled",
    "paused",
]

ReviewStatus = Literal["none", "pending", "approved", "rejected", "overridden"]


class ArtifactPointer(BaseModel):
    kind: str
    relative_path: str
    url: str = ""
    sha256: str = ""
    size_bytes: int = 0
    active: bool = False


class JobRecord(BaseModel):
    job_id: str
    project_id: str = ""
    product: str = ""
    phase: Phase
    review_status: ReviewStatus
    active_attempt_id: str = ""
    active_versions: dict[str, str] = Field(default_factory=dict)
    last_error: str = ""
    artifacts: list[ArtifactPointer] = []


class WorkerLease(BaseModel):
    worker_id: str
    lease_id: str
    attempt_id: str
    task_id: str
    current_phase: Phase
    lease_expires_at: str = ""
