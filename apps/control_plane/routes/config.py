from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from packages.provider_config import (
    load_provider_config,
    mask_provider_config,
    provider_options_payload,
    save_provider_config,
)
from packages.provider_config.scene_config import (
    SceneConfigValidationError,
    validate_scene_folders,
    validate_scene_payload,
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
    normalized_payload = _normalize_payload(payload, root_dir)
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

    # TTS provider validation is no longer needed here — TTS is managed
    # exclusively via PUT /api/tts/config (#386).


def _normalize_payload(payload: dict, root_dir: Path) -> dict:
    normalized = deepcopy(payload)
    _normalize_runtime_settings(normalized, root_dir)
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


def _normalize_runtime_settings(payload: dict, root_dir: Path) -> None:
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
                value = section[field_name]
            if field.get("kind") == "json":
                _validate_json_setting(qualified_name, value, field, root_dir)
                continue
            if field.get("kind") != "number":
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid number field: {qualified_name}",
                )
            if field.get("integer") and not float(value).is_integer():
                raise HTTPException(
                    status_code=400,
                    detail=f"integer required: {qualified_name}",
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


def _validate_json_setting(
    qualified_name: str, value: object, field: dict, root_dir: Path
) -> None:
    if field.get("json_type") == "array" and not isinstance(value, list):
        raise HTTPException(
            status_code=400,
            detail=f"array required: {qualified_name}",
        )
    if not isinstance(value, list) or field.get("item_type") != "object":
        return
    required_keys = field.get("required_item_keys", [])
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=400,
                detail=f"object item required: {qualified_name}[{index}]",
            )
        missing = [key for key in required_keys if not item.get(key)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"missing {missing[0]}: {qualified_name}[{index}]",
            )
    if qualified_name == "scene.folders":
        try:
            validate_scene_folders(value, root_dir)
        except SceneConfigValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_product_config(reader) -> dict:
    """Return the active product's merged config, or root-level config if none active.

    Categories are resolved through the same three-tier priority chain used by
    the asset library endpoints (product → asset_library → defaults), so the
    response always reflects the categories actually in effect.  This prevents
    the frontend from accidentally overwriting configured categories with an
    empty list when saving unrelated product fields.
    """
    reader.reload()
    active_id = reader.active_product_id
    if active_id:
        config = reader.get_product_config(product_id=active_id)
    else:
        config = reader.get_product_config()

    if not config.get("categories"):
        from packages.pipeline_services.asset_library.category_config import (
            get_categories,
        )

        resolved = get_categories(reader, product_id=active_id)
        config["categories"] = [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "vision_prompt": c.vision_prompt,
            }
            for c in resolved
        ]

    return config


@router.get("/api/config/product")
def get_product_config(request: Request) -> dict:
    reader = request.app.state.config_reader
    return _resolve_product_config(reader)


@router.put("/api/config/product")
def put_product_config(request: Request, payload: dict) -> dict:
    product_store = request.app.state.product_store
    reader = request.app.state.config_reader
    _validate_product_scene_config(payload, request.app.state.root_dir)
    product_store.set_product_config(payload)
    return _resolve_product_config(reader)


@router.delete("/api/config/product")
def delete_product_config(request: Request) -> dict:
    request.app.state.product_store.reset_product_config()
    return {"status": "ok"}


def _validate_product_scene_config(payload: dict, root_dir: Path) -> None:
    try:
        validate_scene_payload(payload, root_dir)
    except SceneConfigValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
