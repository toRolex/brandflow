from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from packages.provider_config.tts_config import TTSConfig, TTSConfigManager
from packages.pipeline_services.tts_monitor import TTSMonitor, TTSMetrics

router = APIRouter(prefix="/api/tts", tags=["tts"])

config_manager = TTSConfigManager()
monitor = TTSMonitor()


class TTSConfigRequest(BaseModel):
    model: str | None = None
    voice: str | None = None
    fallback_voice: str | None = None
    randomize_voice: bool | None = None
    random_voices: list[str] | None = None
    voice_design_prompt: str | None = None
    style_prompt: str | None = None
    audio_format: str | None = None
    sample_rate: int | None = None
    bitrate: int | None = None
    channel: int | None = None


class TTSConfigResponse(BaseModel):
    model: str
    voice: str
    fallback_voice: str
    randomize_voice: bool
    random_voices: list[str]
    voice_design_prompt: str
    style_prompt: str
    audio_format: str
    sample_rate: int | None
    bitrate: int | None
    channel: int | None


class TTSPreviewRequest(BaseModel):
    text: str
    model: str = "mimo-v2.5-tts"
    voice: str | None = None
    style_prompt: str | None = None
    voice_design_prompt: str | None = None


PRESET_VOICES = [
    {"id": "mimo_default", "label": "MiMo 默认音色", "note": "官方默认音色，中国区通常映射为冰糖"},
    {"id": "冰糖", "label": "冰糖", "note": "中文女声，清亮自然"},
    {"id": "茉莉", "label": "茉莉", "note": "中文女声，柔和亲切"},
    {"id": "苏打", "label": "苏打", "note": "中文男声，适合短视频口播"},
    {"id": "白桦", "label": "白桦", "note": "中文男声，稳重讲解"},
    {"id": "Mia", "label": "Mia", "note": "英文女声"},
    {"id": "Chloe", "label": "Chloe", "note": "英文女声"},
    {"id": "Milo", "label": "Milo", "note": "英文男声"},
    {"id": "Dean", "label": "Dean", "note": "英文男声"},
]


@router.get("/config", response_model=TTSConfigResponse)
async def get_tts_config(project_id: str | None = None):
    config = config_manager.get_config(project_id)
    return TTSConfigResponse(**config.to_dict())


@router.put("/config")
async def save_tts_config(request: TTSConfigRequest, project_id: str | None = None):
    current = config_manager.get_config(project_id)
    update_data = request.model_dump(exclude_none=True)

    for key, value in update_data.items():
        setattr(current, key, value)

    config_manager.save_config(current, project_id)
    return {"success": True}


@router.get("/voices")
async def get_voices():
    return {"preset_voices": PRESET_VOICES}


@router.get("/metrics")
async def get_tts_metrics(
    project_id: str | None = None,
    range: str = "24h"
) -> dict[str, Any]:
    metrics = monitor.get_metrics(project_id, range)
    return {
        "time_range": metrics.time_range,
        "total_requests": metrics.total_requests,
        "success_count": metrics.success_count,
        "failure_count": metrics.failure_count,
        "success_rate": metrics.success_rate,
        "avg_latency_ms": metrics.avg_latency_ms,
        "avg_audio_duration_ms": metrics.avg_audio_duration_ms,
        "total_audio_duration_ms": metrics.total_audio_duration_ms,
        "error_distribution": metrics.error_distribution,
        "voice_distribution": metrics.voice_distribution,
    }


@router.get("/logs")
async def get_tts_logs(
    project_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> list[dict[str, Any]]:
    logs = monitor.get_logs(project_id, limit, offset, status)
    return [log.to_dict() for log in logs]


@router.get("/errors/distribution")
async def get_error_distribution(
    project_id: str | None = None,
    range: str = "7d"
) -> dict[str, Any]:
    metrics = monitor.get_metrics(project_id, range)
    total_errors = sum(metrics.error_distribution.values())

    distribution = []
    for error_type, count in metrics.error_distribution.items():
        distribution.append({
            "type": error_type,
            "count": count,
            "percentage": count / total_errors if total_errors > 0 else 0
        })

    return {"distribution": distribution, "total": total_errors}


@router.post("/preview")
async def preview_tts(request: TTSPreviewRequest):
    try:
        from packages.pipeline_services.tts_provider import MiMoTTSProvider

        api_key = os.getenv("MIMO_API_KEY", "")
        if not api_key:
            raise HTTPException(status_code=500, detail="未配置 MIMO_API_KEY")

        provider = MiMoTTSProvider(api_key=api_key)
        config = config_manager.get_config()

        if request.model:
            config.model = request.model
        if request.voice:
            config.voice = request.voice
        if request.style_prompt:
            config.style_prompt = request.style_prompt
        if request.voice_design_prompt:
            config.voice_design_prompt = request.voice_design_prompt

        return {
            "success": True,
            "message": "预览功能需要配置真实的MIMO_API_KEY",
            "config": config.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
