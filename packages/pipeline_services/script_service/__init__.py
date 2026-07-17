from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from packages.pipeline_services.script_service.generator import (
    ScriptGenerator,
    ScriptResult,
)
from packages.provider_config.config_resolver import ConfigResolver

__all__ = [
    "ScriptGenerator",
    "ScriptResult",
    "build_generator_config",
    "generate_script",
    "generate_cover_title",
]


def build_generator_config(config_resolver: ConfigResolver, product: str) -> Any:
    """Build a duck-typed config object for ScriptGenerator from ConfigResolver."""
    llm_config, api_key, api_url = config_resolver.llm(product_id=product or None)
    return SimpleNamespace(
        api_key=api_key,
        base_url=api_url,
        model=llm_config.get("model", "deepseek-v4-pro"),
    )


def generate_script(
    product: str,
    output_dir: Path,
    *,
    language: str,
    brand: str,
    config_resolver: ConfigResolver,
    custom_prompt: str = "",
) -> dict[str, Any]:
    """Generate a script via LLM and persist txt/json artifacts to *output_dir*.

    LLM config is resolved via *config_resolver*.
    """
    config = build_generator_config(config_resolver, product)
    generator = ScriptGenerator(config)
    result = generator.run(
        product=product,
        brand=brand,
        mock=False,
        custom_prompt=custom_prompt,
        language=language,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    txt_path = output_dir / "口播文案.txt"
    txt_path.write_text(result.full_text, encoding="utf-8")

    json_path = output_dir / "口播文案.json"
    json_path.write_text(
        json.dumps(
            {
                "product": product,
                "brand": brand,
                "mode": "script_service",
                "language": language,
                "final_script": result.full_text,
                "first_half": result.first_half,
                "second_half": result.second_half,
                "attempts": result.attempts,
                "quality": result.quality,
                "mock": result.mock,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "final_script": result.full_text,
        "txt_path": str(txt_path),
        "json_path": str(json_path),
        "first_half": result.first_half,
        "second_half": result.second_half,
        "attempts": result.attempts,
        "quality": result.quality,
        "mock": result.mock,
    }


def generate_cover_title(
    script_text: str,
    product: str,
    brand: str,
    config_resolver: ConfigResolver,
) -> dict[str, Any]:
    """Generate a cover title from *script_text*.

    LLM config is resolved via *config_resolver*.
    """
    config = build_generator_config(config_resolver, product)
    generator = ScriptGenerator(config)
    return generator.generate_cover_title(script_text, product, brand)
