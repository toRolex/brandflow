from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import List, Optional

from packages.script_template.models import ScriptTemplate


class ScriptTemplateStore:
    """ScriptTemplate 存储 — 每个模板一个 JSON 文件在 config/templates/ 下。"""

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

    def generate_id(self) -> str:
        return f"tmpl_{uuid.uuid4().hex[:12]}"
