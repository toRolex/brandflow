from __future__ import annotations

from packages.script_template.models import ScriptTemplate, TemplateSlot, TemplateVariable
from packages.script_template.renderer import render_template


def _sample_template() -> ScriptTemplate:
    return ScriptTemplate(
        id="tmpl_001",
        name="通用带货脚本",
        description="适用于食品类短视频带货",
        slots=[
            TemplateSlot(type="hook", label="开头钩子", required=True, max_length=60, hint="吸引眼球的开头"),
            TemplateSlot(type="selling_point", label="核心卖点", required=True, max_length=200, hint="产品核心卖点描述"),
            TemplateSlot(type="usage_scene", label="使用场景", required=False, max_length=100, hint="产品的使用场景"),
            TemplateSlot(type="call_to_action", label="行动号召", required=True, max_length=60, hint="引导用户购买"),
        ],
        variables=[
            TemplateVariable(name="product_name", label="产品名", source="product_config"),
            TemplateVariable(name="brand_name", label="品牌名", source="product_config"),
            TemplateVariable(name="audience", label="目标受众", source="manual"),
        ],
        default_config_override={"word_count_max": 200},
    )


def test_render_with_variable_values() -> None:
    """传入变量值应正确渲染到结果中"""
    tmpl = _sample_template()
    result = render_template(
        tmpl,
        slot_contents={
            "开头钩子": "你知道吗？很多人都在找{product_name}这款产品！",
            "核心卖点": "我们的{brand_name}{product_name}采用了最新科技，口感极佳。",
            "使用场景": "早上搭配{product_name}，营养又美味。",
            "行动号召": "点击下方链接购买{product_name}吧！",
        },
        variable_values={
            "product_name": "羊肚菌",
            "brand_name": "菌王山珍",
        },
    )
    assert "羊肚菌" in result
    assert "菌王山珍" in result
    assert "{product_name}" not in result
    assert "{brand_name}" not in result


def test_render_required_slots_only() -> None:
    """可选 slot 未填写时应跳过"""
    tmpl = _sample_template()
    result = render_template(
        tmpl,
        slot_contents={
            "开头钩子": "开头内容",
            "核心卖点": "卖点内容",
            "行动号召": "购买呼吁",
        },
        variable_values={},
    )
    assert "开头内容" in result
    assert "卖点内容" in result
    assert "购买呼吁" in result
    # 使用场景未提供，不应出现在结果中
    # (或者可以填空字符串，取决于实现)


def test_render_empty_slots() -> None:
    """没有 slot 的模板返回空字符串"""
    tmpl = ScriptTemplate(
        id="empty", name="空模板", description="", slots=[], variables=[], default_config_override={}
    )
    result = render_template(tmpl, {}, {})
    assert result == ""


def test_render_partial_variables() -> None:
    """部分变量值缺失时应优雅处理"""
    tmpl = _sample_template()
    result = render_template(
        tmpl,
        slot_contents={
            "开头钩子": "欢迎观看{product_name}的介绍",
            "核心卖点": "来自{brand_name}品牌",
            "行动号召": "快来购买吧",
        },
        variable_values={"product_name": "松茸"},
    )
    # product_name 被替换
    assert "{product_name}" not in result
    assert "松茸" in result
    # brand_name 未提供，占位符保留
    assert "{brand_name}" in result
    assert result  # 非空
