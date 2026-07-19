from __future__ import annotations

import re
from pathlib import Path
from typing import Any

TARGET_MIN_CHARS = 150
TARGET_MAX_CHARS = 200
FORBIDDEN_TERMS = [
    "治疗",
    "治愈",
    "疗效",
    "降血糖",
    "降血压",
    "抗癌",
    "药到病除",
    "治療",
    "治癒",
    "療效",
    "藥到病除",
]
EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f5ff"
    "\U0001f600-\U0001f64f"
    "\U0001f680-\U0001f6ff"
    "\U0001f700-\U0001f77f"
    "\U0001f780-\U0001f7ff"
    "\U0001f800-\U0001f8ff"
    "\U0001f900-\U0001f9ff"
    "\U0001fa00-\U0001fa6f"
    "\U0001fa70-\U0001faff"
    "☀-⛿"
    "✀-➿"
    "]+",
    flags=re.UNICODE,
)


def compact_len(text: str) -> int:
    """去标点后计算紧凑字数。"""
    cleaned = re.sub(
        r"[，。！？、；：,.!?%()\-\s\"\"''《》【】…·\n]", "", str(text or "")
    )
    return len(cleaned)


def _max_sentence_length_errors(
    text: str, max_sentence_length: int | None
) -> list[str]:
    """如果配置了 max_sentence_length，检查每句紧凑字数是否超标。"""
    if max_sentence_length is None:
        return []
    errors: list[str] = []
    # 按句末标点分割
    sentences = re.split(r"[。！？.!?\n]+", text)
    for i, sentence in enumerate(sentences):
        sentence = sentence.strip()
        if sentence and compact_len(sentence) > max_sentence_length:
            errors.append(
                f"第{i + 1}句超长：{compact_len(sentence)} > {max_sentence_length}"
            )
    return errors


def _resolve_config(config: dict | None, key: str, default: Any) -> Any:
    """从 config["script"] 读取配置值，不存在时返回 default。"""
    if config is None:
        return default
    script_cfg = config.get("script", {})
    return script_cfg.get(key, default)


def _check_knowledge_rules(
    text: str,
    config: dict | None,
) -> list[str]:
    """Check knowledge-based quality rules.

    Reads knowledge_rules from config and validates against the KnowledgeStore.
    Returns a list of error strings (empty = no errors).
    Silently skips if knowledge_rules is not configured or store is empty.
    """
    if config is None:
        return []
    k_rules = config.get("knowledge_rules", {})
    if not k_rules:
        return []

    store_dir = k_rules.get("store_dir", "")
    if not store_dir:
        return []

    errors: list[str] = []

    try:
        from packages.knowledge_store.store import KnowledgeStore

        store = KnowledgeStore(Path(store_dir))
    except Exception:
        return []

    top_k = k_rules.get("top_k", 5)

    # Check require_top_selling_points
    require_top = k_rules.get("require_top_selling_points", False)
    if require_top:
        top_points = store.get_top_k_items(item_type="selling_point", k=top_k)
        if top_points:
            missing = []
            for p in top_points:
                if p.title not in text and p.content not in text:
                    missing.append(p.title)
            if missing:
                errors.append(
                    f"缺少核心卖点：{', '.join(missing[:3])}"
                    + (f" 等 {len(missing)} 个" if len(missing) > 3 else "")
                )

    # Check min_selling_points_included
    min_points = k_rules.get("min_selling_points_included", 0)
    if min_points > 0:
        all_points = store.get_top_k_items(item_type="selling_point", k=top_k)
        if all_points:
            included_count = sum(
                1 for p in all_points if p.title in text or p.content in text
            )
            if included_count < min_points:
                errors.append(
                    f"脚本中仅包含 {included_count} 个卖点，要求至少 {min_points} 个"
                )

    # Check forbidden_words_from_knowledge
    forbid_from_knowledge = k_rules.get("forbidden_words_from_knowledge", False)
    if forbid_from_knowledge:
        all_items = store.list_items()
        forbidden_terms = [
            item.content.strip()
            for item in all_items
            if item.type.value == "forbidden_word" and item.content.strip()
        ]
        if forbidden_terms:
            for term in forbidden_terms:
                if term in text:
                    errors.append(f"包含知识库禁词「{term}」")

    return errors


def validate_script(
    text: str, product: str, brand: str, config: dict | None = None
) -> dict[str, Any]:
    """硬条件质检，返回 {"ok": bool, "errors": [...]}。

    当 config 非空时，从 config["script"] 读取质检规则覆盖硬编码默认值。
    """
    errors: list[str] = []
    clen = compact_len(text)

    word_count_min = _resolve_config(config, "word_count_min", TARGET_MIN_CHARS)
    word_count_max = _resolve_config(config, "word_count_max", TARGET_MAX_CHARS)
    forbidden_terms = _resolve_config(config, "forbidden_words", FORBIDDEN_TERMS)
    required_word_count = _resolve_config(config, "required_word_count", None)
    emoji_forbidden = _resolve_config(config, "emoji_forbidden", True)
    max_sentence_len = _resolve_config(config, "max_sentence_length", None)

    # 字数范围
    if clen < word_count_min:
        errors.append(f"字数不足：{clen} < {word_count_min}")
    if clen > word_count_max:
        errors.append(f"字数超标：{clen} > {word_count_max}")

    # 品名出现次数
    if required_word_count is not None:
        product_required = required_word_count.get("product", 1)
        brand_required = required_word_count.get("brand", 1)
    else:
        product_required = 1
        brand_required = 1

    product_count = text.count(product)
    if product_count < product_required:
        errors.append(f"品名「{product}」未出现")
    elif product_required > 0 and product_count > product_required:
        errors.append(
            f"品名「{product}」出现 {product_count} 次，要求恰好 {product_required} 次"
        )

    brand_count = text.count(brand)
    if brand:
        if brand_count < brand_required:
            errors.append(f"品牌「{brand}」未出现")
        elif brand_required > 0 and brand_count > brand_required:
            errors.append(
                f"品牌「{brand}」出现 {brand_count} 次，要求恰好 {brand_required} 次"
            )

    # emoji 检查
    if emoji_forbidden and EMOJI_RE.search(text):
        errors.append("包含 emoji 表情")

    # 禁词检查
    for term in forbidden_terms:
        if term in text:
            errors.append(f"包含医疗禁词「{term}」")

    # 每句长度检查
    errors.extend(_max_sentence_length_errors(text, max_sentence_len))

    # 知识库规则检查
    errors.extend(_check_knowledge_rules(text, config))

    return {"ok": len(errors) == 0, "errors": errors}


def validate_cantonese_script(
    text: str, product: str, brand: str, config: dict | None = None
) -> dict[str, Any]:
    """粤语版宽松质检，接受 config 参数覆盖质检规则。"""
    errors: list[str] = []
    clen = compact_len(text)

    word_count_min = _resolve_config(config, "word_count_min", TARGET_MIN_CHARS)
    word_count_max = _resolve_config(config, "word_count_max", TARGET_MAX_CHARS)
    forbidden_terms = _resolve_config(config, "forbidden_words", FORBIDDEN_TERMS)
    required_word_count = _resolve_config(config, "required_word_count", None)
    emoji_forbidden = _resolve_config(config, "emoji_forbidden", True)
    max_sentence_len = _resolve_config(config, "max_sentence_length", None)

    if clen < word_count_min:
        errors.append(f"字数不足：{clen} < {word_count_min}")
    if clen > word_count_max:
        errors.append(f"字数超标：{clen} > {word_count_max}")

    # 品名/品牌（粤语无上限要求）
    if required_word_count is not None:
        product_required = required_word_count.get("product", 1)
        brand_required = required_word_count.get("brand", 1)
        product_count = text.count(product)
        if product_count < product_required:
            errors.append(f"品名「{product}」未出现")
        brand_count = text.count(brand)
        if brand and brand_count < brand_required:
            errors.append(f"品牌「{brand}」未出现")
    else:
        if product not in text:
            errors.append(f"品名「{product}」未出现")
        if brand and brand not in text:
            errors.append(f"品牌「{brand}」未出现")

    if emoji_forbidden and EMOJI_RE.search(text):
        errors.append("包含 emoji 表情")

    for term in forbidden_terms:
        if term in text:
            errors.append(f"包含医疗禁词「{term}」")

    errors.extend(_max_sentence_length_errors(text, max_sentence_len))

    # 知识库规则检查
    errors.extend(_check_knowledge_rules(text, config))

    return {"ok": len(errors) == 0, "errors": errors}
