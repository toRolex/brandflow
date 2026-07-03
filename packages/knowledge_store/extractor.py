from __future__ import annotations

import json
import uuid
from typing import Any

from packages.knowledge_store.models import KnowledgeItem
from packages.pipeline_services.llm_client import LLMClient

_EXTRACTION_SYSTEM_PROMPT = """你是一个产品知识提取专家。从给定的产品介绍文本中提取结构化知识。

请提取以下类别的信息（每类 3-10 条，按重要程度降序排列）：
1. selling_point — 产品核心卖点（最优先）
2. specification — 产品规格参数
3. forbidden_word — 产品相关的禁忌词（如竞品名称、违规词等）
4. brand_tone — 品牌调性描述
5. usage_scene — 使用场景描述

返回 JSON 格式：
{
  "items": [
    {
      "type": "selling_point",
      "title": "简短标题（10字以内）",
      "content": "详细描述（50-100字）",
      "priority": 5,
      "tags": ["标签1", "标签2"]
    }
  ]
}

priority 取值范围 1-5（5=最重要）。
title 不超过 10 个字，content 不超过 100 个字。
每类至少 3 条，最多 10 条。"""


def _chunk_text(text: str, max_chars: int = 2000) -> list[str]:
    """Split text into chunks of at most max_chars characters."""
    if not text.strip():
        return []
    chunks = []
    for i in range(0, len(text), max_chars):
        chunks.append(text[i : i + max_chars])
    return chunks


def _generate_item_id() -> str:
    return f"ki_{uuid.uuid4().hex[:12]}"


def _parse_llm_response(raw: str) -> list[dict[str, Any]]:
    """Parse LLM response JSON and return items list."""
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            return []
        payload = json.loads(raw[start : end + 1])
        items = payload.get("items", [])
        if not isinstance(items, list):
            return []
        return items
    except (json.JSONDecodeError, ValueError):
        return []


class KnowledgeExtractor:
    """Extract structured knowledge from raw text using LLM."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._client = llm_client

    def extract(self, text: str, source_document: str = "") -> list[KnowledgeItem]:
        """Extract knowledge items from text.

        Args:
            text: Raw text content to extract from.
            source_document: Filename or identifier of the source.

        Returns:
            List of KnowledgeItem extracted from the text.
        """
        if not text.strip():
            return []

        chunks = _chunk_text(text)
        all_items: list[KnowledgeItem] = []

        for chunk in chunks:
            items = self._extract_from_chunk(chunk, source_document)
            all_items.extend(items)

        return all_items

    def _extract_from_chunk(
        self, chunk: str, source_document: str
    ) -> list[KnowledgeItem]:
        if self._client is None:
            return []

        messages = [
            {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"请提取以下产品介绍中的结构化知识：\n\n{chunk}",
            },
        ]

        try:
            raw = self._client.chat(messages)
        except Exception:
            return []

        raw_items = _parse_llm_response(raw)
        result: list[KnowledgeItem] = []
        for raw_item in raw_items:
            try:
                item = KnowledgeItem(
                    id=_generate_item_id(),
                    document_id="",
                    type=raw_item.get("type", "selling_point"),
                    title=raw_item.get("title", ""),
                    content=raw_item.get("content", ""),
                    priority=raw_item.get("priority", 3),
                    tags=raw_item.get("tags", []),
                    source_document=source_document,
                )
                result.append(item)
            except Exception:
                continue

        # Sort by priority descending
        result.sort(key=lambda x: x.priority, reverse=True)
        return result
