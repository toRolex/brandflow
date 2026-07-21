"""Asset retrieval phase handler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from packages.domain_core.models import ArtifactPointer
from packages.pipeline_services.asset_library import (
    AssetRepository,
    AssetRetriever,
)
from packages.pipeline_services.asset_library.classify import create_classify_fn

from .shared import _discover_script, _fallback_category_suggestion_model, _job_dir, _to_artifact

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """Execute semantic retrieval: script text -> keyword match -> selected clips."""
    job_dir = _job_dir(ctx)
    workspace_dir = ctx.root_dir / "workspace"

    script_text = _discover_script(job_dir)

    if not script_text:
        print("[ASSET] No script text found — emitting sentinel", flush=True)
        return [
            ArtifactPointer(
                kind="asset_retrieval_done",
                relative_path="",
                url="",
                size_bytes=0,
            )
        ]

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

    selected = retriever.retrieve(script_text, ctx.product)

    clip_list_path = job_dir / "selected_clips.json"
    clip_list_path.write_text(
        json.dumps(selected, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[ASSET] Retrieved {len(selected)} clips -> {clip_list_path}", flush=True
    )
    return [_to_artifact("selected_clips", clip_list_path, workspace_dir)]
