from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from packages.provider_config.catalog import default_provider_document, provider_options_payload
from packages.provider_config.runtime_env import LLM_ENV_MAPPINGS, TTS_ENV_MAPPINGS, VISION_ENV_MAPPINGS

SECRET_MASK = "***"
CLEAR_SECRET_SENTINEL = "__CLEAR__"


def _provider_sections() -> dict:
    return default_provider_document()["providers"]


def _options_sections() -> dict:
    return provider_options_payload()["providers"]


def _known_secret_fields() -> set[str]:
    secrets: set[str] = set()
    for section in _options_sections().values():
        for provider in section["providers"].values():
            for field in provider["fields"]:
                if field.get("secret"):
                    secrets.add(field["name"])
    return secrets


def _known_json_fields() -> set[str]:
    json_fields: set[str] = set()
    for section in _options_sections().values():
        for provider in section["providers"].values():
            for field in provider["fields"]:
                if field.get("kind") == "json":
                    json_fields.add(field["name"])
    return json_fields


def _merge_payload(payload: Any, previous: dict | None = None) -> dict:
    merged = default_provider_document()
    merged_sections = merged["providers"]
    previous_sections = (previous or default_provider_document()).get("providers", {})
    incoming_sections = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(incoming_sections, dict):
        return merged

    secret_fields = _known_secret_fields()
    json_fields = _known_json_fields()
    for section_name, section_default in merged_sections.items():
        incoming_section = incoming_sections.get(section_name)
        if not isinstance(incoming_section, dict):
            continue

        selected = incoming_section.get("selected")
        if isinstance(selected, str) and (selected == "" or selected in section_default["providers"]):
            merged_sections[section_name]["selected"] = selected

        incoming_providers = incoming_section.get("providers")
        if not isinstance(incoming_providers, dict):
            continue

        for provider_name, provider_default in section_default["providers"].items():
            incoming_provider = incoming_providers.get(provider_name)
            if not isinstance(incoming_provider, dict):
                continue

            previous_provider = (
                previous_sections.get(section_name, {})
                .get("providers", {})
                .get(provider_name, {})
            )
            for field_name in provider_default:
                if field_name not in incoming_provider:
                    continue
                value = incoming_provider.get(field_name)
                if field_name in json_fields:
                    if value == "":
                        merged_sections[section_name]["providers"][provider_name][field_name] = ""
                        continue
                    if isinstance(value, (dict, list)):
                        merged_sections[section_name]["providers"][provider_name][field_name] = value
                        continue
                    if isinstance(value, str):
                        try:
                            merged_sections[section_name]["providers"][provider_name][field_name] = json.loads(value)
                        except json.JSONDecodeError:
                            merged_sections[section_name]["providers"][provider_name][field_name] = value
                    continue
                if not isinstance(value, str):
                    continue
                if field_name in secret_fields:
                    if value == CLEAR_SECRET_SENTINEL:
                        merged_sections[section_name]["providers"][provider_name][field_name] = CLEAR_SECRET_SENTINEL
                        continue
                    if value in {"", SECRET_MASK}:
                        previous_value = previous_provider.get(field_name)
                        if isinstance(previous_value, str) and previous_value:
                            value = previous_value
                merged_sections[section_name]["providers"][provider_name][field_name] = value
    return merged


def _inject_env_secrets(payload: dict, root_dir: Path) -> dict:
    """Read secret values from .env and inject them as masked placeholders into the payload."""
    env_path = Path(root_dir) / ".env"
    if not env_path.exists():
        return payload

    env_values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env_values[key.strip()] = value.strip()

    result = deepcopy(payload)
    for (section_name, provider_name, field_name), env_key in _SECRET_ENV_MAP.items():
        env_val = env_values.get(env_key, "")
        if env_val:
            provider = result.get("providers", {}).get(section_name, {}).get("providers", {}).get(provider_name, {})
            if isinstance(provider, dict) and field_name in provider:
                provider[field_name] = SECRET_MASK

    return result


def load_provider_config(root_dir: Path) -> dict:
    config_path = Path(root_dir) / "config" / "providers.yaml"
    if not config_path.exists():
        return default_provider_document()

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    merged = _merge_payload(data)
    return _inject_env_secrets(merged, root_dir)


def _build_secret_env_map() -> dict[tuple[str, str, str], str]:
    """Build reverse mapping for secret fields only: (section, provider, field_name) → ENV_VAR_NAME."""
    section_mappings: dict[str, dict] = {
        "llm": LLM_ENV_MAPPINGS,
        "tts": TTS_ENV_MAPPINGS,
        "vision": VISION_ENV_MAPPINGS,
    }
    secret_fields = _known_secret_fields()
    result: dict[tuple[str, str, str], str] = {}
    for section_name, mappings in section_mappings.items():
        for provider_name, entry in mappings.items():
            for env_var, field_name in entry.get("env", {}).items():
                if field_name in secret_fields:
                    result[(section_name, provider_name, field_name)] = env_var
    return result


_SECRET_ENV_MAP = _build_secret_env_map()


def _sync_secrets_to_env(root_dir: Path, payload: dict) -> dict:
    """Extract real secret values from payload, write them to .env, return payload with secrets cleared."""
    env_path = Path(root_dir) / ".env"
    existing_lines: list[str] = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()

    secret_updates: dict[str, str] = {}
    secrets_to_clear: set[str] = set()
    providers = payload.get("providers", {})
    for section_name, section in providers.items():
        for provider_name, provider in section.get("providers", {}).items():
            for field_name, value in provider.items():
                if value == CLEAR_SECRET_SENTINEL:
                    env_key = _SECRET_ENV_MAP.get((section_name, provider_name, field_name))
                    if env_key:
                        secrets_to_clear.add(env_key)
                    continue
                if not isinstance(value, str) or not value or value == SECRET_MASK:
                    continue
                env_key = _SECRET_ENV_MAP.get((section_name, provider_name, field_name))
                if env_key is None:
                    continue
                secret_updates[env_key] = value

    if not secret_updates and not secrets_to_clear:
        return payload

    # Write updated .env
    new_lines: list[str] = []
    seen: set[str] = set()
    for line in existing_lines:
        stripped = line.strip()
        if stripped.startswith("#") or stripped == "" or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in secrets_to_clear:
            seen.add(key)
            continue
        if key in secret_updates:
            new_lines.append(f"{key}={secret_updates[key]}")
            seen.add(key)
        else:
            new_lines.append(line)

    for key, value in secret_updates.items():
        if key not in seen:
            new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines).rstrip("\n") + "\n", encoding="utf-8")

    # Clear secret values from payload so they are not written to providers.yaml
    result = deepcopy(payload)
    for section_name, section in result.get("providers", {}).items():
        for provider_name, provider in section.get("providers", {}).items():
            for field_name in list(provider.keys()):
                if _SECRET_ENV_MAP.get((section_name, provider_name, field_name)):
                    provider[field_name] = ""

    return result


def save_provider_config(root_dir: Path, payload: dict) -> None:
    root = Path(root_dir)
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "providers.yaml"
    existing = load_provider_config(root)
    normalized = validate_provider_payload(payload, previous=existing)
    # Sync real secret values to .env, clear them from YAML
    normalized = _sync_secrets_to_env(root, normalized)
    temp_path = config_path.with_suffix(".yaml.tmp")
    temp_path.unlink(missing_ok=True)
    temp_path.write_text(
        yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    temp_path.replace(config_path)


def mask_provider_config(payload: dict) -> dict:
    masked = deepcopy(payload)
    secret_fields = _known_secret_fields()
    for section in masked.get("providers", {}).values():
        for provider in section.get("providers", {}).values():
            for field_name in secret_fields:
                value = provider.get(field_name)
                if isinstance(value, str) and value:
                    provider[field_name] = SECRET_MASK
    return masked


def validate_provider_payload(payload: dict, previous: dict | None = None) -> dict:
    return _merge_payload(payload, previous=previous)
