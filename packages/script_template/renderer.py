from __future__ import annotations

from typing import Dict

from packages.script_template.models import ScriptTemplate


def render_template(
    template: ScriptTemplate,
    slot_contents: Dict[str, str],
    variable_values: Dict[str, str],
) -> str:
    """将模板渲染为 manual_script 文本。

    1. 对每个 slot，从 slot_contents 获取内容
    2. 将内容中的 {variable_name} 替换为 variable_values 中的值
    3. 收集所有填写的 slot 内容，按模板 slots 顺序排列
    """
    if not template.slots:
        return ""

    rendered_parts: list[str] = []
    for slot in template.slots:
        content = slot_contents.get(slot.label, "")
        if not content:
            continue
        # 替换变量占位符
        for var_name, var_value in variable_values.items():
            placeholder = "{" + var_name + "}"
            if placeholder in content:
                content = content.replace(placeholder, var_value)
        rendered_parts.append(content)

    return "\n\n".join(rendered_parts)
