"""Route for AI-powered asset category suggestion."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from packages.pipeline_services.asset_library.category_config import (
    get_categories,
)
from packages.pipeline_services.asset_library.category_suggestion import (
    suggest_categories,
)
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore

router = APIRouter(prefix="/api/assets/categories", tags=["api-assets"])


class SuggestRequest(BaseModel):
    sample_size: int | None = Field(
        default=None, description="Number of assets to sample (default from config)"
    )
    model: str | None = Field(
        default=None,
        description="LLM model to use for clustering (default from config)",
    )


class SuggestResponseItem(BaseModel):
    label: str = Field(default="")
    description: str = Field(default="")
    vision_prompt: str = Field(default="")


class SuggestResponse(BaseModel):
    suggestions: list[SuggestResponseItem] = Field(default_factory=list)
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
    config_reader: ConfigReader = request.app.state.config_reader
    secret_store: SecretStore = request.app.state.secret_store

    sample_size = (
        body.sample_size or config_reader.get_category_suggestion_sample_size()
    )
    llm_model = body.model or config_reader.get_category_suggestion_model()

    # Build LLM config override with the specified model
    llm_config = {
        "provider": config_reader.get_llm_config().get("provider", "deepseek"),
        "api_key": secret_store.get_llm_api_key(config_reader),
        "endpoint": secret_store.get_llm_endpoint(config_reader),
        "model": llm_model,
    }

    result = suggest_categories(
        root_dir=root_dir,
        sample_size=sample_size,
        llm_config=llm_config,
    )

    raw_categories = result.get("categories", [])
    mapped_suggestions = [
        SuggestResponseItem(
            label=str(c.get("name", "")),
            description=str(c.get("description", "")),
            vision_prompt=str(c.get("vision_prompt", "")),
        )
        for c in raw_categories
    ]

    return SuggestResponse(
        suggestions=mapped_suggestions,
        sampled_assets=result.get("sampled_assets", 0),
        model_used=result.get("model_used", llm_model),
        descriptions=result.get("descriptions", []),
        errors=result.get("errors", []),
    )


@router.get("")
async def list_categories(request: Request) -> list[dict]:
    """Return the currently configured asset categories.

    Uses the app config directory so that product-level categories are respected
    when running with a non-default ``config_dir`` (e.g. in tests).
    """
    root_dir: Path = request.app.state.root_dir
    config_reader = ConfigReader(config_dir=str(root_dir / "config"))
    active_id = config_reader.active_product_id
    return [
        {"id": c.id, "name": c.name, "description": c.description}
        for c in get_categories(config_reader, product_id=active_id or None)
    ]
