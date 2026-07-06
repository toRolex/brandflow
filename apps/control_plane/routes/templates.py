from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from packages.script_template.models import ScriptTemplate
from packages.script_template.renderer import render_template
from packages.script_template.store import ScriptTemplateStore

router = APIRouter(prefix="/api/config/templates", tags=["templates"])


def _store(request: Request) -> ScriptTemplateStore:
    templates_dir = Path(str(request.app.state.root_dir)) / "config" / "templates"
    return ScriptTemplateStore(templates_dir)


@router.get("")
def list_templates(request: Request):
    return [t.model_dump() for t in _store(request).list_templates()]


@router.get("/{template_id}")
def get_template(request: Request, template_id: str):
    tmpl = _store(request).get_template(template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="template not found")
    return tmpl.model_dump()


@router.post("")
def create_template(request: Request, payload: ScriptTemplate):
    store = _store(request)
    created = store.create_template(payload)
    return created.model_dump()


@router.put("/{template_id}")
def update_template(request: Request, template_id: str, payload: ScriptTemplate):
    store = _store(request)
    if template_id != payload.id:
        payload.id = template_id
    result = store.update_template(payload)
    if result is None:
        raise HTTPException(status_code=404, detail="template not found")
    return result.model_dump()


@router.delete("/{template_id}")
def delete_template(request: Request, template_id: str):
    if not _store(request).delete_template(template_id):
        raise HTTPException(status_code=404, detail="template not found")
    return {"status": "ok"}


class PreviewRequest(BaseModel):
    slot_contents: dict[str, str] = {}
    variable_values: dict[str, str] = {}


@router.post("/{template_id}/preview")
def preview_template(request: Request, template_id: str, payload: PreviewRequest):
    store = _store(request)
    tmpl = store.get_template(template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="template not found")

    rendered = render_template(
        tmpl,
        slot_contents=payload.slot_contents,
        variable_values=payload.variable_values,
    )
    return {"rendered_script": rendered}
