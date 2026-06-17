from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.pipeline_services.script_service import ScriptGenerator


class LegacyScriptBridge:
    def __init__(self, root_dir: Path):
        self._root_dir = root_dir

    def generate(
        self,
        product: str,
        output_dir: Path,
        mock: bool = False,
        custom_prompt: str = "",
    ) -> dict[str, Any]:
        from packages.provider_config.app_config import AppConfigManager

        config = AppConfigManager()
        llm_config = config.get_llm_config()

        class _Config:
            api_key = config.get_llm_api_key()
            base_url = config.get_llm_endpoint()
            model = llm_config.get("model", "deepseek-v4-pro")

        generator = ScriptGenerator(_Config())
        result = generator.run(
            product=product,
            brand="滋元堂",
            mock=mock,
            custom_prompt=custom_prompt,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        txt_path = output_dir / "口播文案.txt"
        txt_path.write_text(result.full_text, encoding="utf-8")

        json_path = output_dir / "口播文案.json"
        json_path.write_text(
            json.dumps(
                {
                    "product": product,
                    "brand": "滋元堂",
                    "mode": "mock" if mock else "script_service",
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
