from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

from packages.pipeline_services.script_service import ScriptGenerator

if TYPE_CHECKING:
    from packages.provider_config.config_reader import ConfigReader
    from packages.provider_config.secret_store import SecretStore


class LegacyScriptBridge:
    def __init__(
        self,
        root_dir: Path,
        config_reader: "ConfigReader | None" = None,
        secret_store: "SecretStore | None" = None,
    ):
        self._root_dir = root_dir
        self._config_reader = config_reader
        self._secret_store = secret_store

    def _get_or_create_reader(self) -> "ConfigReader":
        if self._config_reader is not None:
            return self._config_reader
        from packages.provider_config.config_reader import ConfigReader

        return ConfigReader(config_dir=str(self._root_dir / "config"))

    def _get_or_create_secrets(self) -> "SecretStore":
        if self._secret_store is not None:
            return self._secret_store
        from packages.provider_config.secret_store import SecretStore

        return SecretStore()

    def generate(
        self,
        product: str,
        output_dir: Path,
        mock: bool = False,
        custom_prompt: str = "",
        language: str = "mandarin",
        brand: str = "",
    ) -> dict[str, Any]:
        reader = self._get_or_create_reader()
        secrets = self._get_or_create_secrets()
        llm_config = reader.get_llm_config()

        class _Config:
            api_key = secrets.get_llm_api_key(reader)
            base_url = secrets.get_llm_endpoint(reader)
            model = llm_config.get("model", "deepseek-v4-pro")

        generator = ScriptGenerator(_Config())
        result = generator.run(
            product=product,
            brand=brand,
            mock=mock,
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
                    "mode": "mock" if mock else "script_service",
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
