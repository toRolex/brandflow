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


def validate_script(text: str, product: str, brand: str) -> dict[str, Any]:
    """硬条件质检，返回 {"ok": bool, "errors": [...]}。"""
    errors: list[str] = []
    clen = compact_len(text)

    if clen < TARGET_MIN_CHARS:
        errors.append(f"字数不足：{clen} < {TARGET_MIN_CHARS}")
    if clen > TARGET_MAX_CHARS:
        errors.append(f"字数超标：{clen} > {TARGET_MAX_CHARS}")

    product_count = text.count(product)
    if product_count < 1:
        errors.append(f"品名「{product}」未出现")
    elif product_count > 1:
        errors.append(f"品名「{product}」出现 {product_count} 次，要求恰好 1 次")

    brand_count = text.count(brand)
    if brand:
        if brand_count < 1:
            errors.append(f"品牌「{brand}」未出现")
        elif brand_count > 1:
            errors.append(f"品牌「{brand}」出现 {brand_count} 次，要求恰好 1 次")

    if EMOJI_RE.search(text):
        errors.append("包含 emoji 表情")

    for term in FORBIDDEN_TERMS:
        if term in text:
            errors.append(f"包含医疗禁词「{term}」")

    return {"ok": len(errors) == 0, "errors": errors}




def validate_cantonese_script(text: str, product: str, brand: str) -> dict[str, Any]:
    """粤语版宽松质检：字数 150-200、品名/品牌出现、烹熟同义表达、无违禁词。"""
    errors: list[str] = []
    clen = compact_len(text)

    if clen < TARGET_MIN_CHARS:
        errors.append(f"字数不足：{clen} < {TARGET_MIN_CHARS}")
    if clen > TARGET_MAX_CHARS:
        errors.append(f"字数超标：{clen} > {TARGET_MAX_CHARS}")

    if product not in text:
        errors.append(f"品名「{product}」未出现")

    if brand and brand not in text:
        errors.append(f"品牌「{brand}」未出现")

    if EMOJI_RE.search(text):
        errors.append("包含 emoji 表情")

    for term in FORBIDDEN_TERMS:
        if term in text:
            errors.append(f"包含医疗禁词「{term}」")

    return {"ok": len(errors) == 0, "errors": errors}
