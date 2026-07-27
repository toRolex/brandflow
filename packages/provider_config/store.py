from __future__ import annotations

import os
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from packages.provider_config.catalog import (
    default_provider_document,
    provider_field_to_runtime_field,
    provider_options_payload,
)
from packages.provider_config.runtime_env import (
    LLM_ENV_MAPPINGS,
    TTS_ENV_MAPPINGS,
    VISION_ENV_MAPPINGS,
)

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
        if isinstance(selected, str) and (
            selected == "" or selected in section_default["providers"]
        ):
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
                        merged_sections[section_name]["providers"][provider_name][
                            field_name
                        ] = ""
                        continue
                    if isinstance(value, (dict, list)):
                        merged_sections[section_name]["providers"][provider_name][
                            field_name
                        ] = value
                        continue
                    if isinstance(value, str):
                        try:
                            merged_sections[section_name]["providers"][provider_name][
                                field_name
                            ] = json.loads(value)
                        except json.JSONDecodeError:
                            merged_sections[section_name]["providers"][provider_name][
                                field_name
                            ] = value
                    continue
                if not isinstance(value, str):
                    continue
                if field_name in secret_fields:
                    if value == CLEAR_SECRET_SENTINEL:
                        merged_sections[section_name]["providers"][provider_name][
                            field_name
                        ] = CLEAR_SECRET_SENTINEL
                        continue
                    if value in {"", SECRET_MASK}:
                        previous_value = previous_provider.get(field_name)
                        if isinstance(previous_value, str) and previous_value:
                            value = previous_value
                merged_sections[section_name]["providers"][provider_name][
                    field_name
                ] = value
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
            provider = (
                result.get("providers", {})
                .get(section_name, {})
                .get("providers", {})
                .get(provider_name, {})
            )
            if isinstance(provider, dict) and field_name in provider:
                provider[field_name] = SECRET_MASK

    return result


def load_provider_config(root_dir: Path) -> dict:
    """Build the provider form document from the canonical app config.

    ``providers.yaml`` is read only as a legacy compatibility input.  Runtime
    selections and the selected provider's non-secret fields always come from
    ``app_config.json``; unselected form profiles live under
    ``provider_profiles`` in that same file.
    """
    from packages.provider_config.config_io import load_config

    root = Path(root_dir)
    legacy_path = root / "config" / "providers.yaml"
    if legacy_path.exists():
        legacy = yaml.safe_load(legacy_path.read_text(encoding="utf-8"))
        merged = _merge_payload(legacy)
    else:
        merged = default_provider_document()

    app_config = load_config(root / "config" / "app_config.json")
    profiles = app_config.get("provider_profiles", {})
    if isinstance(profiles, dict):
        for section_name, provider_profiles in profiles.items():
            if not isinstance(provider_profiles, dict):
                continue
            section = merged.get("providers", {}).get(section_name, {})
            known_providers = section.get("providers", {})
            for provider_name, profile in provider_profiles.items():
                if provider_name in known_providers and isinstance(profile, dict):
                    known_providers[provider_name].update(deepcopy(profile))

    for section_name in ("llm", "tts", "vision"):
        runtime = app_config.get(section_name)
        if not isinstance(runtime, dict):
            continue
        selected = runtime.get("provider")
        section = merged["providers"][section_name]
        if not isinstance(selected, str) or selected not in section["providers"]:
            continue
        section["selected"] = selected
        selected_profile = section["providers"][selected]
        for field_name in selected_profile:
            runtime_name = provider_field_to_runtime_field(field_name)
            if runtime_name in runtime:
                selected_profile[field_name] = deepcopy(runtime[runtime_name])

    return _inject_env_secrets(merged, root)


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
                    env_key = _SECRET_ENV_MAP.get(
                        (section_name, provider_name, field_name)
                    )
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
                env_key = _SECRET_ENV_MAP.get((section_name, provider_name, field_name))
                if env_key is None:
                    continue
                env_val = os.environ.get(env_key, "").strip()
                if env_val:
                    provider[field_name] = ""

    return result


def _sync_to_app_config(root_dir: Path, providers_payload: dict) -> None:
    """Persist non-secret provider settings into the canonical app config."""
    from packages.provider_config.config_io import load_config, save_config

    config_path = root_dir / "config" / "app_config.json"
    app_config = load_config(config_path)
    providers = providers_payload.get("providers", {})

    secret_fields = _known_secret_fields()
    managed_runtime_fields: dict[str, set[str]] = {}
    for section_name in ("llm", "tts", "vision"):
        names: set[str] = set()
        for provider in providers.get(section_name, {}).get("providers", {}).values():
            names.update(
                provider_field_to_runtime_field(name)
                for name in provider
                if name not in secret_fields
            )
        managed_runtime_fields[section_name] = names

    profiles: dict[str, dict[str, dict[str, Any]]] = {}
    for section_name, section in providers.items():
        selected = section.get("selected", "")
        provider_values = section.get("providers", {})
        profiles[section_name] = {}
        for provider_name, provider in provider_values.items():
            if provider_name == selected or not isinstance(provider, dict):
                continue
            profiles[section_name][provider_name] = {
                key: deepcopy(value)
                for key, value in provider.items()
                if key not in secret_fields
            }

        if section_name not in ("llm", "tts", "vision"):
            continue
        if not selected or selected not in provider_values:
            continue

        runtime = app_config.setdefault(section_name, {})
        for field_name in managed_runtime_fields[section_name]:
            runtime.pop(field_name, None)
        runtime["provider"] = selected
        for field_name, value in provider_values[selected].items():
            if field_name in secret_fields:
                continue
            runtime_name = provider_field_to_runtime_field(field_name)
            runtime[runtime_name] = deepcopy(value)

    app_config["provider_profiles"] = profiles

    save_config(config_path, app_config)


def save_provider_config(root_dir: Path, payload: dict) -> None:
    root = Path(root_dir)
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    existing = load_provider_config(root)
    normalized = validate_provider_payload(payload, previous=existing)
    # Secrets are the only values persisted outside app_config.json.
    normalized = _sync_secrets_to_env(root, normalized)
    _sync_to_app_config(root, normalized)


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
