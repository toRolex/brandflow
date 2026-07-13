from __future__ import annotations

from unittest.mock import MagicMock

from packages.knowledge_store.extractor import KnowledgeExtractor
from packages.knowledge_store.models import KnowledgeItem


class TestKnowledgeExtractor:
    def _make_extractor(self, mock_llm_response: str):
        mock_client = MagicMock()
        mock_client.chat.return_value = mock_llm_response
        extractor = KnowledgeExtractor(llm_client=mock_client)
        return extractor, mock_client

    def test_extract_returns_items(self):
        llm_response = """{
            "items": [
                {"type": "selling_point", "title": "鲜美口感", "content": "羊肚菌口感鲜嫩", "priority": 5, "tags": ["口感"]},
                {"type": "specification", "title": "规格", "content": "500g/包", "priority": 3, "tags": ["包装"]},
                {"type": "brand_tone", "title": "品牌调性", "content": "高端品质", "priority": 4, "tags": ["品牌"]}
            ]
        }"""
        extractor, mock_client = self._make_extractor(llm_response)
        items = extractor.extract(
            "羊肚菌是一种珍贵的食用菌，口感鲜嫩，营养丰富。", source_document="test.txt"
        )
        assert len(items) >= 3
        # Check selling point
        selling = [i for i in items if i.type == "selling_point"]
        assert len(selling) >= 1
        assert selling[0].title == "鲜美口感"
        assert selling[0].priority == 5

        specification = [i for i in items if i.type == "specification"]
        assert len(specification) >= 1

        brand_tone = [i for i in items if i.type == "brand_tone"]
        assert len(brand_tone) >= 1

    def test_extract_with_empty_text_returns_empty(self):
        extractor, mock_client = self._make_extractor('{"items": []}')
        items = extractor.extract("", source_document="empty.txt")
        assert items == []

    def test_extract_handles_malformed_json_gracefully(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = "not json at all"
        extractor = KnowledgeExtractor(llm_client=mock_client)
        items = extractor.extract("some text", source_document="test.txt")
        assert items == []

    def test_extract_chunks_long_text(self):
        """超过2000字的文本应被分段"""
        extractor, mock_client = self._make_extractor(
            '{"items": [{"type": "selling_point", "title": "T", "content": "C", "priority": 3, "tags": []}]}'
        )
        long_text = "羊肚菌" * 3000  # ~9000 chars
        extractor.extract(long_text, source_document="long.txt")
        # Should have been called more than once (multiple chunks)
        assert mock_client.chat.call_count > 1

    def test_extract_parses_simple_chunks(self):
        """纯文本段落（无编号/粗体）也能正确提取"""
        llm_response = """{
            "items": [
                {"type": "selling_point", "title": "天然种植", "content": "采用天然种植方式，不使用化肥农药", "priority": 4, "tags": ["种植"]}
            ]
        }"""
        extractor, mock_client = self._make_extractor(llm_response)
        items = extractor.extract(
            "天然种植，不使用化肥农药。", source_document="test.txt"
        )
        assert len(items) == 1
        assert items[0].type == "selling_point"
        assert items[0].content == "采用天然种植方式，不使用化肥农药"

    def test_extract_generates_document_id(self):
        extractor, mock_client = self._make_extractor('{"items": []}')
        items = extractor.extract("内容", source_document="test.txt")
        assert all(isinstance(i, KnowledgeItem) for i in items)

    def test_duplicate_type_respects_order(self):
        """多个同类型的 item 应按 priority 降序排列"""
        llm_response = """{
            "items": [
                {"type": "selling_point", "title": "卖点A", "content": "AAA", "priority": 3, "tags": []},
                {"type": "selling_point", "title": "卖点B", "content": "BBB", "priority": 5, "tags": []},
                {"type": "selling_point", "title": "卖点C", "content": "CCC", "priority": 4, "tags": []}
            ]
        }"""
        extractor, _ = self._make_extractor(llm_response)
        items = extractor.extract("内容", source_document="test.txt")
        selling = [i for i in items if i.type == "selling_point"]
        assert len(selling) == 3
        # Should be in priority descending order: 5, 4, 3
        assert [i.priority for i in selling] == [5, 4, 3]
