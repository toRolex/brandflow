"""Script generation phase handler."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packages.pipeline_services.script_service import generate_script
from packages.pipeline_services.script_service.generator import ScriptGenerator
from packages.provider_config.config_reader import ConfigReader, ConfigResolver

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """Execute script generation (manual or LLM) and optional cover title."""
    workspace_dir = ctx.root_dir / "workspace"
    job_dir = orchestrator._job_dir(ctx)
    manual_script: str = ctx.options.get("manual_script", "")
    result: list = []

    # 1. Generate or write script
    if manual_script:
        language = ctx.options.get("language", "mandarin")
        if language == "cantonese":
            try:
                llm_cfg = orchestrator._resolve_llm_config(ctx)

                class _LLMConfig:
                    api_key = orchestrator._resolve_api_key(llm_cfg)
                    base_url = orchestrator._resolve_api_url(llm_cfg)
                    model = llm_cfg.get("model", "deepseek-v4-pro")

                gen = ScriptGenerator(_LLMConfig())
                manual_script = gen.to_cantonese(
                    manual_script, ctx.product, ctx.brand
                )
                print("[SCRIPT] Converted manual script to Cantonese", flush=True)
            except Exception as e:
                print(
                    f"[SCRIPT WARN] Cantonese conversion failed, using original: {e}",
                    flush=True,
                )

        txt_path = job_dir / "口播文案.txt"
        txt_path.write_text(manual_script, encoding="utf-8")
        json_path = job_dir / "口播文案.json"
        json_path.write_text(
            json.dumps(
                {"text": manual_script, "source": "manual"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        script_result: dict[str, Any] = {
            "txt_path": str(txt_path),
            "json_path": str(json_path),
            "final_script": manual_script,
        }
    else:
        language = ctx.options.get("language", "mandarin")
        config_resolver = ConfigResolver(
            reader=orchestrator._config
            if orchestrator._config is not None
            else ConfigReader(),
            secrets=orchestrator._secrets,
        )
        script_result = generate_script(
            product=ctx.product,
            output_dir=job_dir,
            language=language,
            brand=ctx.brand,
            config_resolver=config_resolver,
        )

    # 2. Emit artifact pointers for txt + json
    txt_path = Path(script_result["txt_path"])
    json_path = Path(script_result["json_path"])
    for p in [txt_path, json_path]:
        if p.exists():
            result.append(orchestrator._to_artifact("script", p, workspace_dir))

    # 3. Auto-generate cover title (if not already set)
    _maybe_generate_cover_title(orchestrator, ctx, script_result)

    return result


def _maybe_generate_cover_title(
    orchestrator: PhaseOrchestrator,
    ctx: PhaseContext,
    script_result: dict[str, Any],
) -> None:
    """Auto-generate cover title if the job JSON has no ``cover_title.text``.

    Uses ConfigReader for LLM config resolution.
    Errors are logged but never propagated.
    """
    job_json_path = ctx.project_dir / "control" / "jobs" / f"{ctx.job_id}.json"
    if not job_json_path.exists():
        return

    job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
    existing_ct = job_data.get("cover_title", {})
    if existing_ct and existing_ct.get("text"):
        return  # already set

    try:
        script_text = script_result.get("final_script", "")
        txt_path = Path(script_result.get("txt_path", ""))
        if not script_text and txt_path.exists():
            script_text = txt_path.read_text(encoding="utf-8").strip()
        if not script_text:
            return

        llm_config = orchestrator._resolve_llm_config(ctx)

        class _CoverConfig:
            api_key = orchestrator._resolve_api_key(llm_config)
            base_url = orchestrator._resolve_api_url(llm_config)
            model = llm_config.get("model", "deepseek-v4-pro")

        gen = ScriptGenerator(_CoverConfig())
        cover_title = gen.generate_cover_title(script_text, ctx.product, ctx.brand)
        job_data["cover_title"] = cover_title
        job_json_path.write_text(
            json.dumps(job_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[COVER_TITLE] Auto-generated: {cover_title['text']}", flush=True)
    except Exception as e:
        print(f"[COVER_TITLE WARN] Failed to auto-generate: {e}", flush=True)
