from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

Language = Literal["mandarin", "cantonese"]

Phase = Literal[
    "queued",
    "script_generating",
    "script_review",
    "scene_assembling",
    "tts_generating",
    "tts_review",
    "subtitle_generating",
    "montage_assembling",
    "asset_retrieving",
    "asset_review",
    "video_rendering",
    "final_rendering",
    "final_review",
    "completed",
    "failed",
    "cancelled",
    "paused",
]

ProductionMode = Literal["import", "generate"]
ReviewStatus = Literal["none", "pending", "approved", "rejected", "overridden"]


AudioSource = Literal["tts", "upload", "library"]


class ArtifactPointer(BaseModel):
    kind: str
    relative_path: str
    url: str = ""
    sha256: str = ""
    size_bytes: int = 0
    active: bool = False


class ExecutionFailure(BaseModel):
    """Stable, user-actionable details for an unsuccessful execution."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, pattern=r"^[A-Z][A-Z0-9_]*$")
    message: str = Field(min_length=1)
    retryable: StrictBool

    @model_validator(mode="after")
    def reject_blank_text(self) -> "ExecutionFailure":
        if not self.code.strip() or not self.message.strip():
            raise ValueError("failure code and message must not be blank")
        return self


ExecutionStatus = Literal[
    "pending",
    "running",
    "retrying",
    "failed",
    "succeeded",
]


class PhaseExecutionState(BaseModel):
    """Lifecycle and attempt information exposed by a Job."""

    model_config = ConfigDict(extra="forbid")

    status: ExecutionStatus = "pending"
    current_attempt: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    error: ExecutionFailure | None = None

    @model_validator(mode="after")
    def validate_status_attempts_and_error(self) -> "PhaseExecutionState":
        if self.current_attempt > self.max_attempts:
            raise ValueError("current_attempt must not exceed max_attempts")
        if self.status in {"running", "retrying", "failed", "succeeded"}:
            if self.current_attempt < 1:
                raise ValueError(f"{self.status} requires at least one attempt")
        if self.status == "retrying" and self.current_attempt >= self.max_attempts:
            raise ValueError("retrying requires a remaining attempt")
        if self.status == "failed" and self.error is None:
            raise ValueError("failed execution requires error details")
        if self.status not in {"failed", "retrying"} and self.error is not None:
            raise ValueError(
                "only failed or retrying execution may include error details"
            )
        if (
            self.status == "retrying"
            and self.error is not None
            and not self.error.retryable
        ):
            raise ValueError("retrying execution requires a retryable error")
        return self


class CoverTitleStyle(BaseModel):
    primary_color: str = "#FFD700"
    outline_color: str = "#000000"
    highlight_color: str = "#FF0000"
    outline_width: float = 2.0
    position: Literal["top", "center", "bottom"] = "center"


class CoverTitle(BaseModel):
    text: str = ""
    highlight_words: list[str] = Field(default_factory=list)
    style: CoverTitleStyle = Field(default_factory=CoverTitleStyle)


class JobRecord(BaseModel):
    job_id: str
    project_id: str = ""
    product: str = ""
    brand: str = ""
    name: str = ""  # 用户自定义名称，空则回退到 product
    mode: ProductionMode = "generate"
    phase: Phase
    failed_phase: Phase | None = None
    review_status: ReviewStatus
    active_attempt_id: str = ""
    active_versions: dict[str, str] = Field(default_factory=dict)
    last_error: str = ""
    execution: PhaseExecutionState = Field(default_factory=PhaseExecutionState)
    artifacts: list[ArtifactPointer] = []
    manual_script: str = ""  # 手动输入的文案，如果非空则跳过LLM生成
    uploaded_audio_path: str = ""  # 上传的音频文件路径，如果非空则跳过TTS生成
    audio_source: AudioSource = "tts"  # tts / upload / library
    skip_subtitle: bool = False
    auto_approve: bool = False
    language: Language = "mandarin"
    cover_title: CoverTitle = Field(default_factory=CoverTitle)
    music_track_path: str = ""
    music_volume: int = 80
    tts_model: str = (
        ""  # job-level TTS model override, empty = use global/product config
    )
    tts_voice: str = (
        ""  # job-level TTS voice override, empty = use global/product config
    )
    used_asset_ids: list[str] = []
    scene_folder_ids: list[str] = Field(default_factory=list)
    transition_duration_ms: int = 500


class WorkerLease(BaseModel):
    worker_id: str
    lease_id: str
    attempt_id: str
    task_id: str
    current_phase: Phase
    lease_expires_at: str = ""
