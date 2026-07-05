from __future__ import annotations

import json
from pathlib import Path

from packages.knowledge_store.models import (
    KnowledgeDocument,
    KnowledgeItem,
    KnowledgeItemType,
    SourceType,
)
from packages.knowledge_store.store import KnowledgeStore


class TestKnowledgeStore:
    def test_save_and_list_documents(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        doc = KnowledgeDocument(
            id="doc_001",
            filename="test.txt",
            source_type=SourceType.TXT,
            parsed_text="测试内容",
        )
        store.save_document(doc)
        docs = store.list_documents()
        assert len(docs) == 1
        assert docs[0].id == "doc_001"

    def test_get_document(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        doc = KnowledgeDocument(
            id="doc_001",
            filename="test.txt",
            source_type=SourceType.TXT,
            parsed_text="测试内容",
        )
        store.save_document(doc)
        loaded = store.get_document("doc_001")
        assert loaded is not None
        assert loaded.parsed_text == "测试内容"

    def test_get_document_not_found(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        assert store.get_document("nonexistent") is None

    def test_save_and_list_items(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        items = [
            KnowledgeItem(
                id="item_001",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title="鲜美",
                content="口感鲜嫩",
                priority=5,
                tags=["口感"],
                source_document="test.txt",
            ),
            KnowledgeItem(
                id="item_002",
                document_id="doc_001",
                type=KnowledgeItemType.SPECIFICATION,
                title="规格",
                content="500g",
                priority=2,
                tags=[],
                source_document="test.txt",
            ),
        ]
        store.save_items(items)
        all_items = store.list_items()
        assert len(all_items) == 2

    def test_list_items_by_document(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        items = [
            KnowledgeItem(
                id="item_001",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title="鲜美",
                content="口感鲜嫩",
                priority=5,
                source_document="a.txt",
            ),
            KnowledgeItem(
                id="item_002",
                document_id="doc_002",
                type=KnowledgeItemType.SPECIFICATION,
                title="规格",
                content="500g",
                priority=2,
                source_document="b.txt",
            ),
        ]
        store.save_items(items)
        doc_items = store.list_items(document_id="doc_001")
        assert len(doc_items) == 1
        assert doc_items[0].id == "item_001"

    def test_get_top_k_selling_points(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        items = [
            KnowledgeItem(
                id=f"item_{i:03d}",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title=f"卖点{i}",
                content=f"卖点内容{i}",
                priority=p,
                source_document="test.txt",
            )
            for i, p in enumerate([5, 3, 4, 1, 2], start=1)
        ]
        store.save_items(items)
        top3 = store.get_top_k_items(item_type=KnowledgeItemType.SELLING_POINT, k=3)
        assert len(top3) == 3
        # Should be sorted by priority descending: 5, 4, 3
        assert [item.priority for item in top3] == [5, 4, 3]

    def test_get_top_k_empty_when_no_items(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        assert store.get_top_k_items(item_type=KnowledgeItemType.SELLING_POINT, k=5) == []

    def test_directory_created_on_init(self, tmp_path: Path) -> None:
        store_path = tmp_path / "knowledge"
        store = KnowledgeStore(store_path)
        assert store_path.exists()
        assert store_path.is_dir()

    def test_multiple_documents_persistence(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        docs = [
            KnowledgeDocument(
                id=f"doc_{i:03d}",
                filename=f"{i}.txt",
                source_type=SourceType.TXT,
                parsed_text=f"内容{i}",
            )
            for i in range(1, 4)
        ]
        for d in docs:
            store.save_document(d)
        # Recreate store to simulate restart
        store2 = KnowledgeStore(tmp_path)
        loaded = store2.list_documents()
        assert len(loaded) == 3

    def test_delete_document_cascades_to_items(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        doc = KnowledgeDocument(
            id="doc_001",
            filename="test.txt",
            source_type=SourceType.TXT,
            parsed_text="测试",
        )
        store.save_document(doc)
        items = [
            KnowledgeItem(
                id="item_001",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title="卖点",
                content="内容",
                priority=3,
                source_document="test.txt",
            ),
        ]
        store.save_items(items)
        store.delete_document("doc_001")
        assert store.get_document("doc_001") is None
        assert store.list_items(document_id="doc_001") == []


class TestKnowledgeStoreFlatFiles:
    """Issue #28 requires flat documents.json / items.json persistence."""

    def test_documents_persisted_to_flat_json(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        doc = KnowledgeDocument(
            id="doc_001",
            filename="test.txt",
            source_type="txt",
            parsed_text="测试内容",
        )
        store.save_document(doc)

        documents_path = tmp_path / "knowledge" / "documents.json"
        assert documents_path.exists()
        data = json.loads(documents_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "doc_001"

    def test_items_persisted_to_flat_json(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        items = [
            KnowledgeItem(
                id="item_001",
                document_id="doc_001",
                type="selling_point",
                title="鲜美",
                content="口感鲜嫩",
                priority=5,
                tags=["口感"],
                source_document="test.txt",
            ),
        ]
        store.save_items(items)

        items_path = tmp_path / "knowledge" / "items.json"
        assert items_path.exists()
        data = json.loads(items_path.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "item_001"

    def test_multiple_documents_in_one_flat_file(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.save_document(
            KnowledgeDocument(
                id="doc_001", filename="a.txt", source_type="txt", parsed_text="A"
            )
        )
        store.save_document(
            KnowledgeDocument(
                id="doc_002", filename="b.txt", source_type="txt", parsed_text="B"
            )
        )

        data = json.loads(
            (tmp_path / "knowledge" / "documents.json").read_text(encoding="utf-8")
        )
        assert {d["id"] for d in data} == {"doc_001", "doc_002"}

    def test_reload_from_flat_files(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        store.save_document(
            KnowledgeDocument(
                id="doc_001", filename="a.txt", source_type="txt", parsed_text="A"
            )
        )
        store.save_items(
            [
                KnowledgeItem(
                    id="item_001",
                    document_id="doc_001",
                    type="selling_point",
                    title="卖点",
                    content="内容",
                    priority=5,
                    source_document="a.txt",
                )
            ]
        )

        store2 = KnowledgeStore(tmp_path)
        assert len(store2.list_documents()) == 1
        assert len(store2.list_items()) == 1
