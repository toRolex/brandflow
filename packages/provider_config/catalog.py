from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

_CATALOG_PATH = Path(__file__).with_name("catalog.json")
_RUNTIME_FIELD_ALIASES = {"style": "style_prompt"}
_SUPPORTED_TTS_PROVIDERS = frozenset({"qwen", "mimo"})


def _runtime_catalog(data: dict) -> dict:
    """Return the catalog view for providers that have an implementation."""
    result = deepcopy(data)
    tts = result.get("providers", {}).get("tts", {})
    providers = tts.get("providers")
    if isinstance(providers, dict):
        tts["providers"] = {
            name: value
            for name, value in providers.items()
            if name in _SUPPORTED_TTS_PROVIDERS
        }
    return result


with _CATALOG_PATH.open(encoding="utf-8") as _fh:
    _DATA: dict = json.load(_fh)


def default_provider_document() -> dict:
    return _runtime_catalog(_DATA["default_document"])


def default_runtime_settings() -> dict:
    """Return user-configurable non-provider defaults from the catalog."""
    settings = deepcopy(_DATA["default_document"]["settings"])
    options = _DATA["provider_options"].get("settings", {})
    for section_name, section in options.items():
        for field in section.get("fields", []):
            if field.get("secret"):
                settings.get(section_name, {}).pop(field["name"], None)
    return settings


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
            runtime_name = provider_field_to_runtime_field(field_name)
            runtime[runtime_name] = deepcopy(value)
        result[section_name] = runtime
    return result


def provider_options_payload() -> dict:
    return _runtime_catalog(_DATA["provider_options"])


def setting_secret_env_var(section_name: str, field_name: str) -> str:
    """Return the catalog-declared env variable for a settings secret."""
    section = _DATA["provider_options"].get("settings", {}).get(section_name, {})
    for field in section.get("fields", []):
        if field["name"] == field_name and field.get("secret"):
            env_var = field.get("env_var")
            if isinstance(env_var, str):
                return env_var
    raise KeyError(f"missing settings secret env mapping: {section_name}.{field_name}")


def provider_field_to_runtime_field(field_name: str) -> str:
    """Map a provider-form field name to its app_config runtime name."""
    return _RUNTIME_FIELD_ALIASES.get(field_name, field_name)


def tts_provider_for_model(model: str) -> str | None:
    """Return the catalog TTS provider whose declared prefix owns *model*."""
    providers = _DATA["provider_options"]["providers"]["tts"]["providers"]
    for provider_name, provider in providers.items():
        if provider_name not in _SUPPORTED_TTS_PROVIDERS:
            continue
        prefixes = provider.get("model_prefixes", [])
        if any(model.startswith(prefix) for prefix in prefixes):
            return provider_name
    return None


def tts_runtime_providers() -> frozenset[str]:
    """Return TTS providers with a declared runtime model contract."""
    providers = _DATA["provider_options"]["providers"]["tts"]["providers"]
    return frozenset(
        provider_name
        for provider_name, provider in providers.items()
        if provider_name in _SUPPORTED_TTS_PROVIDERS and provider.get("model_prefixes")
    )


def tts_preset_voices(provider_name: str) -> list[dict]:
    """Return preset voices for a TTS provider from the catalog."""
    providers = _DATA["provider_options"]["providers"]["tts"]["providers"]
    if provider_name not in _SUPPORTED_TTS_PROVIDERS:
        return []
    provider = providers.get(provider_name)
    if provider is None:
        return []
    return list(provider.get("preset_voices", []))


def tts_models() -> list[dict]:
    """Return runtime TTS model cards declared in the catalog.

    Each entry: {provider, model, label, description, features}.
    Drives the frontend model picker and per-model capability checks.
    """
    providers = _DATA["provider_options"]["providers"]["tts"]["providers"]
    result: list[dict] = []
    for provider_name, provider in providers.items():
        if provider_name not in _SUPPORTED_TTS_PROVIDERS:
            continue
        for model in provider.get("models", []):
            result.append(
                {
                    "provider": provider_name,
                    "model": model["id"],
                    "label": model.get("label", model["id"]),
                    "description": model.get("description", ""),
                    "features": list(model.get("features", [])),
                }
            )
    return result


# Provider form fields that are NOT connection parameters — they are either
# secrets, identity (model/voice), or business fields owned by other sections.
_TTS_NON_CONNECTION_FIELDS = frozenset(
    {
        "api_key",
        "model",
        "voice",
        "style",
        "audio_format",
        "instructions",
        "language_type",
    }
)


def tts_connection_fields(provider_name: str) -> list[str]:
    """Return the connection-parameter field names for a TTS provider.

    Derived from the catalog field list minus secrets/identity/business fields,
    so adding a field to the catalog automatically surfaces it in the UI.
    """
    providers = _DATA["provider_options"]["providers"]["tts"]["providers"]
    if provider_name not in _SUPPORTED_TTS_PROVIDERS:
        return []
    provider = providers.get(provider_name)
    if provider is None:
        return []
    return [
        field["name"]
        for field in provider.get("fields", [])
        if field["name"] not in _TTS_NON_CONNECTION_FIELDS
    ]
