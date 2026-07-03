from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["mandarin", "cantonese"]

Phase = Literal[
    "queued",
    "script_generating",
    "script_review",
    "tts_generating",
    "tts_review",
    "subtitle_generating",
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

ReviewStatus = Literal["none", "pending", "approved", "rejected", "overridden"]


AudioSource = Literal["tts", "upload", "library"]


class ArtifactPointer(BaseModel):
    kind: str
    relative_path: str
    url: str = ""
    sha256: str = ""
    size_bytes: int = 0
    active: bool = False


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
    name: str = ""  # 用户自定义名称，空则回退到 product
    phase: Phase
    review_status: ReviewStatus
    active_attempt_id: str = ""
    active_versions: dict[str, str] = Field(default_factory=dict)
    last_error: str = ""
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
    used_asset_ids: list[str] = []


class WorkerLease(BaseModel):
    worker_id: str
    lease_id: str
    attempt_id: str
    task_id: str
    current_phase: Phase
    lease_expires_at: str = ""
