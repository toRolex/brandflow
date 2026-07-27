from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

_CATALOG_PATH = Path(__file__).with_name("catalog.json")

with _CATALOG_PATH.open(encoding="utf-8") as _fh:
    _DATA: dict = json.load(_fh)


def default_provider_document() -> dict:
    return deepcopy(_DATA["default_document"])


def default_runtime_provider_config() -> dict:
    """Return runtime defaults derived from the selected catalog profiles."""
    document = _DATA["default_document"]["providers"]
    options = _DATA["provider_options"]["providers"]
    result: dict[str, dict] = {}
    for section_name in ("llm", "tts", "vision"):
        section = document[section_name]
        selected = section["selected"]
        profile = section["providers"][selected]
        secret_fields = {
            field["name"]
            for field in options[section_name]["providers"][selected]["fields"]
            if field.get("secret")
        }
        runtime = {"provider": selected}
        for field_name, value in profile.items():
            if field_name in secret_fields:
                continue
            runtime_name = "style_prompt" if field_name == "style" else field_name
            runtime[runtime_name] = deepcopy(value)
        result[section_name] = runtime
    return result


def provider_options_payload() -> dict:
    return deepcopy(_DATA["provider_options"])
