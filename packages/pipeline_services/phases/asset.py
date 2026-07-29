"""Asset retrieval phase handler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from packages.pipeline_services.asset_library import (
    AssetRepository,
    AssetRetriever,
)
from packages.pipeline_services.asset_library.classify import create_classify_fn
from packages.pipeline_services.logging_utils import get_pipeline_logger

from .shared import (
    _discover_script,
    _fallback_category_suggestion_model,
    _job_dir,
    _to_artifact,
)

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )

_LOGGER = get_pipeline_logger(__name__)


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """Execute semantic retrieval: script text -> keyword match -> selected clips."""
    job_dir = _job_dir(ctx)
    logger = _LOGGER.bind(ctx.job_id)

    script_text = _discover_script(job_dir)

    if not script_text:
        clip_list_path = job_dir / "selected_clips.json"
        clip_list_path.write_text(
            json.dumps([], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.warning(
            "[ASSET] No script text — wrote empty clip list to %s", clip_list_path
        )
        return [_to_artifact("selected_clips", clip_list_path, ctx.layout)]

    db_path = ctx.root_dir / "workspace" / "shared_assets" / "asset_index.db"

    llm_config = orchestrator._resolve_llm_config(ctx)

    api_key = orchestrator._resolve_api_key(llm_config)
    api_url = orchestrator._resolve_api_url(llm_config)

    classify_fn = None
    if api_key and api_url:
        if not api_url.endswith("/chat/completions"):
            api_url = f"{api_url}/chat/completions"

        category_names = orchestrator._resolve_categories(ctx)

        classify_fn = create_classify_fn(
            api_url=api_url,
            api_key=api_key,
            model=orchestrator._config.get_category_suggestion_model()
            if orchestrator._config is not None
            else _fallback_category_suggestion_model(),
            category_names=category_names,
        )

    repo = AssetRepository(db_path)
    retriever = AssetRetriever(repo, classify_fn=classify_fn)

    # If this job is being re-generated (e.g. review rejection), the previous
    # selection is about to be overwritten. Decrement usage for the old refs so
    # usage_count does not drift upward across regeneration cycles.
    old_clips_path = job_dir / "selected_clips.json"
    if old_clips_path.exists():
        try:
            old_clips = json.loads(old_clips_path.read_text(encoding="utf-8"))
        except Exception:
            old_clips = []
        for old_clip in old_clips:
            old_asset_id = old_clip.get("asset_id")
            if old_asset_id:
                repo.decrement_usage(old_asset_id)

    selected = retriever.retrieve(script_text, ctx.product)

    clip_list_path = job_dir / "selected_clips.json"
    clip_list_path.write_text(
        json.dumps(selected, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info("[ASSET] Retrieved %s clips -> %s", len(selected), clip_list_path)
    return [_to_artifact("selected_clips", clip_list_path, ctx.layout)]
