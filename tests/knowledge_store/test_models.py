from __future__ import annotations

from packages.knowledge_store.models import (
    KnowledgeConfig,
    KnowledgeDocument,
    KnowledgeItem,
    SourceType,
)


class TestSourceType:
    def test_source_type_values(self):
        assert SourceType.TXT == "txt"
        assert SourceType.PDF == "pdf"
        assert SourceType.DOCX == "docx"

    def test_source_type_from_string(self):
        assert SourceType("txt") == SourceType.TXT
        assert SourceType("pdf") == SourceType.PDF
        assert SourceType("docx") == SourceType.DOCX


class TestKnowledgeDocument:
    def test_create_document(self):
        doc = KnowledgeDocument(
            id="doc_001",
            filename="test.txt",
            source_type="txt",
            parsed_text="测试内容",
        )
        assert doc.id == "doc_001"
        assert doc.filename == "test.txt"
        assert doc.source_type == "txt"
        assert doc.parsed_text == "测试内容"
        assert doc.created_at is not None

    def test_to_dict_roundtrip(self):
        doc = KnowledgeDocument(
            id="doc_001",
            filename="test.txt",
            source_type="txt",
            parsed_text="测试内容",
        )
        d = doc.to_dict()
        restored = KnowledgeDocument.from_dict(d)
        assert restored.id == doc.id
        assert restored.filename == doc.filename
        assert restored.parsed_text == doc.parsed_text

    def test_create_document_with_pdf_source(self):
        doc = KnowledgeDocument(
            id="doc_pdf",
            filename="test.pdf",
            source_type=SourceType.PDF,
            parsed_text="PDF parsed text",
        )
        assert doc.source_type == SourceType.PDF
        assert doc.source_type == "pdf"

    def test_create_document_with_docx_source(self):
        doc = KnowledgeDocument(
            id="doc_docx",
            filename="test.docx",
            source_type=SourceType.DOCX,
            parsed_text="DOCX parsed text",
        )
        assert doc.source_type == SourceType.DOCX
        assert doc.source_type == "docx"

    def test_pdf_source_to_dict_roundtrip(self):
        doc = KnowledgeDocument(
            id="doc_pdf",
            filename="test.pdf",
            source_type=SourceType.PDF,
            parsed_text="PDF text",
        )
        d = doc.to_dict()
        restored = KnowledgeDocument.from_dict(d)
        assert restored.source_type == SourceType.PDF
        assert d["source_type"] == "pdf"


class TestKnowledgeItem:
    def test_create_selling_point(self):
        item = KnowledgeItem(
            id="item_001",
            document_id="doc_001",
            type="selling_point",
            title="鲜美口感",
            content="羊肚菌口感鲜嫩，带有独特的菌菇香气",
            priority=5,
            tags=["口感", "品质"],
            source_document="test.txt",
        )
        assert item.id == "item_001"
        assert item.type == "selling_point"
        assert item.priority == 5

    def test_default_priority(self):
        item = KnowledgeItem(
            id="item_002",
            document_id="doc_001",
            type="specification",
            title="规格",
            content="500g/包",
            source_document="test.txt",
        )
        assert item.priority == 3  # default

    def test_default_tags(self):
        item = KnowledgeItem(
            id="item_003",
            document_id="doc_001",
            type="brand_tone",
            title="品牌调性",
            content="高端",
            source_document="test.txt",
        )
        assert item.tags == []

    def test_to_dict_roundtrip(self):
        item = KnowledgeItem(
            id="item_001",
            document_id="doc_001",
            type="selling_point",
            title="鲜美口感",
            content="羊肚菌口感鲜嫩",
            priority=5,
            tags=["口感"],
            source_document="test.txt",
        )
        d = item.to_dict()
        restored = KnowledgeItem.from_dict(d)
        assert restored.id == item.id
        assert restored.type == item.type
        assert restored.content == item.content

    def test_invalid_type_rejected(self):
        import pydantic

        try:
            KnowledgeItem(
                id="item_bad",
                document_id="doc_001",
                type="invalid_type",
                title="test",
                content="test",
                source_document="test.txt",
            )
            assert False, "Should have raised"
        except pydantic.ValidationError:
            pass


class TestKnowledgeConfig:
    def test_default_config(self):
        cfg = KnowledgeConfig()
        assert cfg.enabled is True
        assert cfg.top_k == 5

    def test_custom_config(self):
        cfg = KnowledgeConfig(enabled=False, top_k=10)
        assert cfg.enabled is False
        assert cfg.top_k == 10
