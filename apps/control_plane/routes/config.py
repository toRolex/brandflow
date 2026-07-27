from __future__ import annotations

import json
from copy import deepcopy

from fastapi import APIRouter, HTTPException, Request

from packages.provider_config import (
    load_provider_config,
    mask_provider_config,
    provider_options_payload,
    save_provider_config,
)
from packages.provider_config.store import CLEAR_SECRET_SENTINEL

router = APIRouter(tags=["config"])


@router.get("/api/config")
def get_config(request: Request) -> dict:
    payload = load_provider_config(request.app.state.root_dir)
    return mask_provider_config(payload)


@router.get("/api/config/options")
def get_config_options() -> dict:
    return provider_options_payload()


@router.put("/api/config")
def put_config(request: Request, payload: dict) -> dict:
    root_dir = request.app.state.root_dir
    normalized_payload = _normalize_payload(payload)
    _ensure_selected_providers_are_valid(normalized_payload)
    save_provider_config(root_dir, normalized_payload)
    request.app.state.config_reader.reload()
    return mask_provider_config(load_provider_config(root_dir))


def _ensure_selected_providers_are_valid(payload: dict) -> None:
    providers = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(providers, dict):
        return

    options = provider_options_payload()["providers"]
    for section_name, section_payload in providers.items():
        if not isinstance(section_payload, dict):
            continue
        selected = section_payload.get("selected")
        if not isinstance(selected, str):
            continue
        allowed = options.get(section_name, {}).get("providers", {})
        if selected and selected not in allowed:
            raise HTTPException(
                status_code=400, detail=f"invalid provider: {section_name}.{selected}"
            )

    tts = providers.get("tts", {})
    selected = tts.get("selected") if isinstance(tts, dict) else None
    provider_configs = tts.get("providers", {}) if isinstance(tts, dict) else {}
    if isinstance(selected, str) and selected in provider_configs:
        from packages.pipeline_services.tts_provider import resolve_tts_provider_name

        try:
            resolve_tts_provider_name(
                {"provider": selected, "model": provider_configs[selected].get("model")}
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def _normalize_payload(payload: dict) -> dict:
    normalized = deepcopy(payload)
    _normalize_runtime_settings(normalized)
    sections = normalized.get("providers") if isinstance(normalized, dict) else None
    if not isinstance(sections, dict):
        return normalized

    options = provider_options_payload()["providers"]
    for section_name, section_options in options.items():
        section_payload = sections.get(section_name)
        if not isinstance(section_payload, dict):
            continue
        provider_payloads = section_payload.get("providers")
        if not isinstance(provider_payloads, dict):
            continue
        for provider_name, provider_options in section_options.get(
            "providers", {}
        ).items():
            provider_payload = provider_payloads.get(provider_name)
            if not isinstance(provider_payload, dict):
                continue
            for field in provider_options.get("fields", []):
                field_name = field["name"]
                if field_name not in provider_payload:
                    continue
                value = provider_payload[field_name]
                if field.get("secret") and value == CLEAR_SECRET_SENTINEL:
                    continue
                if field.get("kind") != "json":
                    continue
                if value == "":
                    continue
                if not isinstance(value, str):
                    continue
                try:
                    provider_payload[field_name] = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise HTTPException(
                        status_code=400, detail="invalid json field"
                    ) from exc
    return normalized


def _normalize_runtime_settings(payload: dict) -> None:
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        return

    options = provider_options_payload().get("settings", {})
    for section_name, section_options in options.items():
        section = settings.get(section_name)
        if not isinstance(section, dict):
            continue
        for field in section_options.get("fields", []):
            field_name = field["name"]
            if field_name not in section:
                continue
            value = section[field_name]
            qualified_name = f"{section_name}.{field_name}"
            if field.get("kind") == "json" and isinstance(value, str):
                try:
                    section[field_name] = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"invalid json field: {qualified_name}",
                    ) from exc
                continue
            if field.get("kind") != "number":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid number field: {qualified_name}",
                )
            minimum = field.get("min")
            maximum = field.get("max")
            if minimum is not None and value < minimum:
                raise HTTPException(
                    status_code=400,
                    detail=f"value below minimum: {qualified_name}",
                )
            if maximum is not None and value > maximum:
                raise HTTPException(
                    status_code=400,
                    detail=f"value above maximum: {qualified_name}",
                )


def _resolve_product_config(reader) -> dict:
    """Return the active product's merged config, or root-level config if none active."""
    reader.reload()
    active_id = reader.active_product_id
    if active_id:
        return reader.get_product_config(product_id=active_id)
    return reader.get_product_config()


@router.get("/api/config/product")
def get_product_config(request: Request) -> dict:
    reader = request.app.state.config_reader
    return _resolve_product_config(reader)


@router.put("/api/config/product")
def put_product_config(request: Request, payload: dict) -> dict:
    product_store = request.app.state.product_store
    reader = request.app.state.config_reader
    product_store.set_product_config(payload)
    return _resolve_product_config(reader)


@router.delete("/api/config/product")
def delete_product_config(request: Request) -> dict:
    request.app.state.product_store.reset_product_config()
    return {"status": "ok"}
