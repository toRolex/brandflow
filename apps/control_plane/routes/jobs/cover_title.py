from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from apps.control_plane.routes.jobs.helpers import (
    _COVER_TITLE_COOLDOWN,
    _COVER_TITLE_RATE_LIMIT,
)
from apps.control_plane.routes.jobs.models import GenerateCoverTitleRequest
from packages.pipeline_services.script_service.generator import ScriptGenerator

router = APIRouter(tags=["api-jobs"])


@router.post("/cover-title/generate")
def generate_cover_title(payload: GenerateCoverTitleRequest, request: Request):
    if not payload.script_text.strip():
        raise HTTPException(status_code=400, detail="script_text is required")

    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    last = _COVER_TITLE_RATE_LIMIT.get(client_ip, 0)
    if now - last < _COVER_TITLE_COOLDOWN:
        raise HTTPException(
            status_code=429, detail=f"请 {_COVER_TITLE_COOLDOWN} 秒后再试"
        )
    _COVER_TITLE_RATE_LIMIT[client_ip] = now

    config_reader = request.app.state.config_reader
    secret_store = request.app.state.secret_store
    llm_config = config_reader.get_llm_config()

    class _Config:
        api_key = secret_store.get_llm_api_key(config_reader)
        base_url = secret_store.get_llm_endpoint(config_reader)
        model = llm_config.get("model", "deepseek-v4-pro")

    gen = ScriptGenerator(_Config())
    result = gen.generate_cover_title(
        payload.script_text, payload.product, payload.brand
    )
    return result
