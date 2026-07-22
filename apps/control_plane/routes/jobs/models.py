from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator

from packages.domain_core.models import (
    AudioSource,
    CoverTitle,
    CoverTitleStyle,
    Language,
    ProductionMode,
    ReviewStrategy,
)


class CoverTitleStyleRequest(BaseModel):
    primary_color: str = "#FFD700"
    outline_color: str = "#000000"
    highlight_color: str = "#FF0000"
    outline_width: float = 2.0
    position: Literal["top", "center", "bottom"] = "center"


class CoverTitleRequest(BaseModel):
    text: str = ""
    highlight_words: list[str] = []
    style: CoverTitleStyleRequest | None = None


class CreateJobRequest(BaseModel):
    platforms: list[str]
    mode: ProductionMode = "generate"
    asset: str | None = None
    manual_script: str = ""
    uploaded_audio_path: str = ""
    name: str = ""
    skip_subtitle: bool = False
    review_strategy: ReviewStrategy = "review_each"
    audio_source: AudioSource = "tts"
    language: Language = "mandarin"
    cover_title: CoverTitleRequest | None = None
    music_track_path: str = ""
    music_volume: int = 80
    tts_model: str = ""
    tts_voice: str = ""

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_auto_approve(cls, data: Any) -> Any:
        if isinstance(data, dict) and "auto_approve" in data:
            raise ValueError("auto_approve is no longer accepted; use review_strategy")
        return data


class BatchJobItem(BaseModel):
    name: str = ""
    manual_script: str = ""
    mode: ProductionMode = "generate"
    skip_subtitle: bool = False
    audio_source: AudioSource = "tts"
    language: Language = "mandarin"
    cover_title: CoverTitleRequest | None = None
    music_track_path: str = ""
    music_volume: int = 80
    tts_model: str = ""
    tts_voice: str = ""


class BatchCreateRequest(BaseModel):
    platforms: list[str]
    mode: ProductionMode = "generate"
    review_strategy: ReviewStrategy = "review_each"
    jobs: list[BatchJobItem]

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_auto_approve(cls, data: Any) -> Any:
        if isinstance(data, dict) and "auto_approve" in data:
            raise ValueError("auto_approve is no longer accepted; use review_strategy")
        return data


class MigrateScenesRequest(BaseModel):
    scene_folder_ids: list[str]


class RenameJobRequest(BaseModel):
    name: str


class UpdateScriptRequest(BaseModel):
    manual_script: str


class GenerateCoverTitleRequest(BaseModel):
    script_text: str
    product: str = ""
    brand: str = ""


class UpdateTTSVoiceRequest(BaseModel):
    model: str | None = None
    voice: str | None = None
    confirm: bool = False


def _cover_title_from_request(req: CoverTitleRequest | None) -> CoverTitle:
    if req is None:
        return CoverTitle()
    style = CoverTitleStyle()
    if req.style is not None:
        style = CoverTitleStyle(
            primary_color=req.style.primary_color,
            outline_color=req.style.outline_color,
            highlight_color=req.style.highlight_color,
            outline_width=req.style.outline_width,
            position=req.style.position,
        )
    return CoverTitle(
        text=req.text,
        highlight_words=req.highlight_words,
        style=style,
    )
