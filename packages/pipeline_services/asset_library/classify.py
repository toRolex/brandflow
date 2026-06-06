"""LLM-based sentence classification for asset category matching.

Provides a factory function that creates a callable for classifying sentences
into one of the 10 asset categories used in the smart asset library.
"""

from __future__ import annotations

import json
import logging
import urllib.request

from packages.pipeline_services.asset_library.models import Category

logger = logging.getLogger(__name__)

CATEGORY_NAMES = [c.value for c in Category]

CLASSIFY_PROMPT = (
    "你是视频素材分类助手。根据文案句子的语义，从以下分类中选择最匹配的一个：\n"
    + ", ".join(CATEGORY_NAMES)
    + "\n\n严格只返回一个JSON对象，不要有任何其他文字：{\"category\": \"分类名\"}"
)


def create_classify_fn(
    api_url: str,
    api_key: str,
    model: str,
):
    """创建基于 DeepSeek 等 LLM 的句子分类函数。

    Args:
        api_url: LLM API 端点。
        api_key: API 密钥。
        model: 模型名称。

    Returns:
        可调用对象 (sentence) -> 分类名或 None。
    """

    def classify_sentence(sentence: str) -> str | None:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": CLASSIFY_PROMPT},
                {"role": "user", "content": sentence},
            ],
            "temperature": 0,
            "max_tokens": 200,
        }
        data = json.dumps(payload).encode("utf-8")
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
            logger.debug("LLM 返回内容: %s", content)
            
            import re
            
            json_match = re.search(r'\{[^}]*"category"\s*:\s*"[^"]*"\s*\}', content)
            if not json_match:
                json_match = re.search(r'\{[^}]+\}', content)
            
            if json_match:
                try:
                    parsed = json.loads(json_match.group())
                    cat_name = parsed.get("category", "")
                    if cat_name in CATEGORY_NAMES:
                        return cat_name
                    logger.warning("LLM 返回无效分类名: %s", cat_name)
                except json.JSONDecodeError as e:
                    logger.warning("JSON 解析失败: %s, 原始内容: %s", e, json_match.group())
            else:
                logger.warning("LLM 返回中未找到 JSON: %s", content[:200])
            return None
        except Exception as exc:
            logger.warning("LLM 句子分类失败: %s", exc)
            return None

    return classify_sentence
