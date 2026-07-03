"""LLM-based sentence classification for asset category matching.

Provides a factory function that creates a callable for classifying sentences
into asset categories. Categories can come from the legacy ``Category`` enum
or configurable ``CategoryConfig``.

Usage::

    fn = create_classify_fn(api_url, api_key, model)
    category_name = fn("翻炒均匀后出锅装盘。")
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request

from packages.pipeline_services.asset_library.models import Category

logger = logging.getLogger(__name__)

FOOD_CATEGORY_NAMES = [c.value for c in Category]


def build_classify_prompt(category_names: list[str] | None = None) -> str:
    """Build the LLM system prompt for sentence classification.

    Parameters
    ----------
    category_names:
        List of valid category names.  Falls back to the legacy food categories
        when ``None`` or empty.

    Returns
    -------
    str
        The formatted system prompt.
    """
    names = _resolve_category_names(category_names)
    return (
        "你是视频素材分类助手。根据文案句子的语义，从以下分类中选择最匹配的一个：\n"
        + ", ".join(names)
        + '\n\n严格只返回一个JSON对象，不要有任何其他文字：{"category": "分类名"}'
    )


def _resolve_category_names(category_names: list[str] | None) -> list[str]:
    if category_names:
        return category_names
    return FOOD_CATEGORY_NAMES


def create_classify_fn(
    api_url: str,
    api_key: str,
    model: str,
    category_names: list[str] | None = None,
):
    """创建基于 DeepSeek 等 LLM 的句子分类函数。

    Args:
        api_url: LLM API 端点。
        api_key: API 密钥。
        model: 模型名称。
        category_names: 可选的有效分类名列表。默认使用旧版食物分类名。

    Returns:
        可调用对象 (sentence) -> 分类名或 None。
    """
    prompt = build_classify_prompt(category_names)
    valid_names = _resolve_category_names(category_names)

    def classify_sentence(sentence: str) -> str | None:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": sentence},
            ],
            "temperature": 0,
            "max_tokens": 200,
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(3):
            req = urllib.request.Request(
                api_url,
                data=data,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                content = body["choices"][0]["message"]["content"]
                logger.debug("LLM 返回内容 (attempt %d): %s", attempt + 1, content)

                json_match = re.search(r'\{[^}]*"category"\s*:\s*"[^"]*"\s*\}', content)
                if not json_match:
                    json_match = re.search(r"\{[^}]+\}", content)

                if json_match:
                    try:
                        parsed = json.loads(json_match.group())
                        cat_name = parsed.get("category", "")
                        if cat_name in valid_names:
                            return cat_name
                        logger.warning(
                            "LLM 返回无效分类名 (attempt %d): %s", attempt + 1, cat_name
                        )
                    except json.JSONDecodeError as e:
                        logger.warning(
                            "JSON 解析失败 (attempt %d): %s, 原始内容: %s",
                            attempt + 1,
                            e,
                            json_match.group(),
                        )
                else:
                    logger.warning(
                        "LLM 返回中未找到 JSON (attempt %d): %s",
                        attempt + 1,
                        content[:200],
                    )
            except Exception as exc:
                logger.warning("LLM 句子分类失败 (attempt %d): %s", attempt + 1, exc)

        return None

    return classify_sentence
