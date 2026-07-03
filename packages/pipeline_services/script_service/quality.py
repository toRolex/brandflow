from __future__ import annotations

import re
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
                f"第{i+1}句超长：{compact_len(sentence)} > {max_sentence_length}"
            )
    return errors


def _resolve_config(
    config: dict | None, key: str, default: Any
) -> Any:
    """从 config["script"] 读取配置值，不存在时返回 default。"""
    if config is None:
        return default
    script_cfg = config.get("script", {})
    return script_cfg.get(key, default)


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

    return {"ok": len(errors) == 0, "errors": errors}
