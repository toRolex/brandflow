"""Route for AI-powered asset category suggestion."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from packages.pipeline_services.asset_library.category_suggestion import (
    suggest_categories,
)
from packages.provider_config.app_config import AppConfigManager

router = APIRouter(prefix="/api/assets/categories", tags=["api-assets"])


class SuggestRequest(BaseModel):
    sample_size: int | None = Field(
        default=None, description="Number of assets to sample (default from config)"
    )
    model: str | None = Field(
        default=None,
        description="LLM model to use for clustering (default from config)",
    )


class SuggestResponse(BaseModel):
    categories: list[dict] = Field(default_factory=list)
    sampled_assets: int = 0
    model_used: str = ""
    descriptions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


@router.post("/suggest")
async def suggest(request: Request, body: SuggestRequest) -> SuggestResponse:
    """Use AI to analyze the asset library and suggest a category system.

    Scans a random sample of video assets, extracts frames, analyzes them
    with the Vision API, and clusters the descriptions into categories
    via the LLM API.
    """
    root_dir: Path = request.app.state.root_dir
    manager = AppConfigManager()

    sample_size = body.sample_size or manager.get_category_suggestion_sample_size()
    llm_model = body.model or manager.get_category_suggestion_model()

    # Build LLM config override with the specified model
    llm_config = {
        "provider": manager.get_llm_config().get("provider", "deepseek"),
        "api_key": manager.get_llm_api_key(),
        "endpoint": manager.get_llm_endpoint(),
        "model": llm_model,
    }

    result = suggest_categories(
        root_dir=root_dir,
        sample_size=sample_size,
        llm_config=llm_config,
    )

    return SuggestResponse(
        categories=result.get("categories", []),
        sampled_assets=result.get("sampled_assets", 0),
        model_used=result.get("model_used", llm_model),
        descriptions=result.get("descriptions", []),
        errors=result.get("errors", []),
    )
