from __future__ import annotations

import tempfile
from pathlib import Path

from packages.script_template.store import ScriptTemplateStore
from packages.script_template.models import (
    ScriptTemplate,
    TemplateSlot,
    TemplateVariable,
)


def _sample_template(id: str = "tmpl_001") -> ScriptTemplate:
    return ScriptTemplate(
        id=id,
        name="通用带货脚本",
        description="适用于食品类短视频带货",
        slots=[
            TemplateSlot(
                type="hook",
                label="开头钩子",
                required=True,
                max_length=60,
                hint="吸引眼球的开头",
            ),
            TemplateSlot(
                type="selling_point",
                label="核心卖点",
                required=True,
                max_length=200,
                hint="产品核心卖点描述",
            ),
        ],
        variables=[
            TemplateVariable(
                name="product_name", label="产品名", source="product_config"
            ),
            TemplateVariable(
                name="brand_name", label="品牌名", source="product_config"
            ),
        ],
        default_config_override={"word_count_max": 200},
    )


def test_list_empty() -> None:
    """初始状态返回空列表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        templates = store.list_templates()
        assert templates == []


def test_create_template() -> None:
    """创建模板后应返回带 ID 的模板"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        tmpl = _sample_template()
        created = store.create_template(tmpl)
        assert created.id == "tmpl_001"
        assert created.name == "通用带货脚本"
        assert len(created.slots) == 2
        assert len(created.variables) == 2


def test_get_template() -> None:
    """通过 ID 获取模板"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        store.create_template(_sample_template())
        tmpl = store.get_template("tmpl_001")
        assert tmpl is not None
        assert tmpl.name == "通用带货脚本"


def test_get_template_not_found() -> None:
    """获取不存在的模板返回 None"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        tmpl = store.get_template("non_existent")
        assert tmpl is None


def test_update_template() -> None:
    """更新模板后返回更新后的模板"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        store.create_template(_sample_template())

        updated = ScriptTemplate(
            id="tmpl_001",
            name="更新后的模板",
            description="新的描述",
            slots=[],
            variables=[],
            default_config_override={},
        )
        result = store.update_template(updated)
        assert result is not None
        assert result.name == "更新后的模板"
        assert result.description == "新的描述"

        # 验证持久化
        fetched = store.get_template("tmpl_001")
        assert fetched is not None
        assert fetched.name == "更新后的模板"


def test_update_template_not_found() -> None:
    """更新不存在的模板返回 None"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        result = store.update_template(_sample_template())
        assert result is None


def test_delete_template() -> None:
    """删除模板后无法获取"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        store.create_template(_sample_template())
        assert store.delete_template("tmpl_001") is True
        assert store.get_template("tmpl_001") is None


def test_delete_template_not_found() -> None:
    """删除不存在的模板返回 False"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        assert store.delete_template("non_existent") is False


def test_list_templates() -> None:
    """创建多个模板后列表应包含所有模板"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        store.create_template(_sample_template("tmpl_001"))
        store.create_template(
            ScriptTemplate(
                id="tmpl_002",
                name="产品测评脚本",
                description="产品测评类短视频",
                slots=[],
                variables=[],
                default_config_override={},
            )
        )
        templates = store.list_templates()
        assert len(templates) == 2
        names = [t.name for t in templates]
        assert "通用带货脚本" in names
        assert "产品测评脚本" in names


def test_auto_create_directory() -> None:
    """目录不存在时自动创建"""
    with tempfile.TemporaryDirectory() as tmpdir:
        templates_dir = Path(tmpdir) / "templates"
        assert not templates_dir.exists()
        store = ScriptTemplateStore(str(templates_dir))
        assert templates_dir.exists()
        store.create_template(_sample_template())
        assert len(store.list_templates()) == 1


def test_persistence() -> None:
    """模板应持久化到文件系统"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store1 = ScriptTemplateStore(tmpdir)
        store1.create_template(_sample_template())

        store2 = ScriptTemplateStore(tmpdir)
        tmpl = store2.get_template("tmpl_001")
        assert tmpl is not None
        assert tmpl.name == "通用带货脚本"


def test_generate_id() -> None:
    """generate_id 应返回合法 ID"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = ScriptTemplateStore(tmpdir)
        id1 = store.generate_id()
        assert id1.startswith("tmpl_")
        id2 = store.generate_id()
        assert id1 != id2
