from __future__ import annotations

import json
from unittest.mock import MagicMock

from packages.knowledge_store.extractor import KnowledgeExtractor
from packages.knowledge_store.models import KnowledgeItemType


class TestKnowledgeExtractionPipeline:
    """Mock LLMClient tests for the knowledge extraction logic."""

    def _make_extractor(self, response_payload: dict) -> KnowledgeExtractor:
        mock_client = MagicMock()
        mock_client.chat.return_value = json.dumps(response_payload, ensure_ascii=False)
        return KnowledgeExtractor(llm_client=mock_client)

    def test_extract_structured_selling_points(self) -> None:
        extractor = self._make_extractor(
            {
                "items": [
                    {
                        "type": "selling_point",
                        "title": "野生环境",
                        "content": "生长在云南海拔2000米以上的原始森林",
                        "priority": 5,
                        "tags": ["产地"],
                    },
                    {
                        "type": "selling_point",
                        "title": "营养丰富",
                        "content": "富含多种氨基酸和微量元素",
                        "priority": 3,
                        "tags": ["营养"],
                    },
                ]
            }
        )
        items = extractor.extract(
            "羊肚菌生长在云南高山原始森林中，营养丰富。", source_document="product.txt"
        )

        assert len(items) == 2
        assert all(i.type == KnowledgeItemType.SELLING_POINT for i in items)
        assert items[0].priority == 5
        assert items[1].priority == 3
        assert items[0].source_document == "product.txt"

    def test_extract_returns_empty_on_llm_error(self) -> None:
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("LLM unavailable")
        extractor = KnowledgeExtractor(llm_client=mock_client)

        items = extractor.extract("some text", source_document="test.txt")
        assert items == []

    def test_extract_sorts_by_priority_descending(self) -> None:
        extractor = self._make_extractor(
            {
                "items": [
                    {
                        "type": "selling_point",
                        "title": "B",
                        "content": "content b",
                        "priority": 2,
                    },
                    {
                        "type": "selling_point",
                        "title": "A",
                        "content": "content a",
                        "priority": 5,
                    },
                    {
                        "type": "selling_point",
                        "title": "C",
                        "content": "content c",
                        "priority": 4,
                    },
                ]
            }
        )
        items = extractor.extract("text", source_document="test.txt")
        priorities = [i.priority for i in items]
        assert priorities == [5, 4, 2]

    def test_extract_skips_invalid_items(self) -> None:
        extractor = self._make_extractor(
            {
                "items": [
                    {
                        "type": "selling_point",
                        "title": "有效",
                        "content": "有效内容",
                        "priority": 5,
                    },
                    {"type": "unknown_type", "title": "无效", "content": "无效内容"},
                ]
            }
        )
        items = extractor.extract("text", source_document="test.txt")
        assert len(items) == 1
        assert items[0].title == "有效"
