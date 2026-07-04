from __future__ import annotations

from typing import Any, Literal

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
