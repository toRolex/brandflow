from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

SlotType = Literal["hook", "selling_point", "usage_scene", "call_to_action"]
VariableSource = Literal["manual", "product_config", "knowledge_base"]


class TemplateSlot(BaseModel):
    type: SlotType
    label: str
    required: bool = False
    max_length: int = 200
    hint: str = ""


class TemplateVariable(BaseModel):
    name: str
    label: str
    source: VariableSource = "manual"


class ScriptTemplate(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    slots: list[TemplateSlot] = Field(default_factory=list)
    variables: list[TemplateVariable] = Field(default_factory=list)
    default_config_override: dict[str, Any] = Field(default_factory=dict)


def render_template(
    template: ScriptTemplate,
    slot_contents: Dict[str, str],
    variable_values: Dict[str, str],
) -> str:
    """Render a template into manual_script text."""
    if not template.slots:
        return ""
    rendered_parts: list[str] = []
    for slot in template.slots:
        content = slot_contents.get(slot.label, "")
        if not content:
            continue
        for var_name, var_value in variable_values.items():
            placeholder = "{" + var_name + "}"
            if placeholder in content:
                content = content.replace(placeholder, var_value)
        rendered_parts.append(content)
    return "\n\n".join(rendered_parts)


class ScriptTemplateStore:
    """ScriptTemplate storage — one JSON file per template in config/templates/."""

    def __init__(self, templates_dir: str | Path) -> None:
        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, template_id: str) -> Path:
        return self.templates_dir / f"{template_id}.json"

    def list_templates(self) -> List[ScriptTemplate]:
        entries: list[tuple[float, ScriptTemplate]] = []
        for f in self.templates_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                entries.append((f.stat().st_mtime, ScriptTemplate.model_validate(data)))
            except (json.JSONDecodeError, Exception):
                continue
        entries.sort(key=lambda item: item[0])
        return [t for _, t in entries]

    def get_template(self, template_id: str) -> Optional[ScriptTemplate]:
        path = self._path(template_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ScriptTemplate.model_validate(data)
        except (json.JSONDecodeError, Exception):
            return None

    def create_template(self, template: ScriptTemplate) -> ScriptTemplate:
        if not template.id:
            template.id = self.generate_id()
        path = self._path(template.id)
        path.write_text(
            template.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )
        return template

    def update_template(self, template: ScriptTemplate) -> Optional[ScriptTemplate]:
        if not self.get_template(template.id):
            return None
        path = self._path(template.id)
        path.write_text(
            template.model_dump_json(indent=2, exclude_none=True),
            encoding="utf-8",
        )
        return template

    def delete_template(self, template_id: str) -> bool:
        path = self._path(template_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    @staticmethod
    def generate_id() -> str:
        return f"tmpl_{uuid.uuid4().hex[:12]}"


__all__ = [
    "ScriptTemplate",
    "TemplateSlot",
    "TemplateVariable",
    "render_template",
    "ScriptTemplateStore",
]
