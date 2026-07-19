from __future__ import annotations

from pathlib import Path

from packages.knowledge_store.models import KnowledgeItem, SourceType, KnowledgeItemType
from packages.knowledge_store.store import KnowledgeStore


class TestKnowledgeStoreSellingPoints:
    """Test new KnowledgeStore methods for selling point management."""

    def _populate(self, store: KnowledgeStore) -> None:
        items = [
            KnowledgeItem(
                id="sp_001",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title="野生生长环境",
                content="生长在云南海拔2000米以上原始森林中",
                priority=5,
                tags=["产地", "天然"],
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="sp_002",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title="高营养价值",
                content="富含18种氨基酸和多种微量元素",
                priority=4,
                tags=["营养"],
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="sp_003",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title="独特菌菇香气",
                content="烹饪后散发浓郁菌菇香气",
                priority=3,
                tags=["口感"],
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="sp_004",
                document_id="doc_002",
                type=KnowledgeItemType.SPECIFICATION,
                title="包装规格",
                content="每包500g",
                priority=2,
                tags=["包装"],
                source_document="规格.txt",
            ),
            KnowledgeItem(
                id="sp_005",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title="农家手工采摘",
                content="每一朵都是由当地农户手工采摘挑选",
                priority=5,
                tags=["产地", "工艺"],
                source_document="产品介绍.txt",
            ),
        ]
        store.save_items(items)

    def test_list_selling_points_returns_only_selling_points(
        self, tmp_path: Path
    ) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        points = store.list_selling_points()
        assert len(points) == 4
        for p in points:
            assert p.type.value == "selling_point"

    def test_list_selling_points_empty_when_none(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        assert store.list_selling_points() == []

    def test_list_selling_points_filter_by_priority_min(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        points = store.list_selling_points(priority_min=4)
        assert len(points) == 3  # priority 5, 5, 4
        for p in points:
            assert p.priority >= 4

    def test_list_selling_points_filter_by_priority_max(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        points = store.list_selling_points(priority_max=3)
        assert len(points) == 1  # only priority 3
        assert points[0].priority == 3

    def test_list_selling_points_filter_by_priority_range(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        points = store.list_selling_points(priority_min=3, priority_max=4)
        assert len(points) == 2
        for p in points:
            assert 3 <= p.priority <= 4

    def test_list_selling_points_filter_by_tags(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        points = store.list_selling_points(tags=["口感"])
        assert len(points) == 1
        assert points[0].id == "sp_003"

    def test_list_selling_points_filter_by_multiple_tags(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        # Items matching ANY of the tags
        points = store.list_selling_points(tags=["口感", "天然"])
        assert len(points) == 2  # sp_001 (天然) + sp_003 (口感)

    def test_list_selling_points_filter_by_priority_and_tags(
        self, tmp_path: Path
    ) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        points = store.list_selling_points(priority_min=4, tags=["天然"])
        assert len(points) == 1  # sp_001 has priority 5 and tag "天然"

    def test_update_item_title(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        updated = store.update_item("sp_001", title="野生环境")
        assert updated.title == "野生环境"
        assert updated.priority == 5  # unchanged

    def test_update_item_priority(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        updated = store.update_item("sp_001", priority=2)
        assert updated.priority == 2

    def test_update_item_tags(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        updated = store.update_item("sp_001", tags=["产地", "天然", "高端"])
        assert updated.tags == ["产地", "天然", "高端"]

    def test_update_item_content(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        updated = store.update_item("sp_001", content="新内容")
        assert updated.content == "新内容"

    def test_update_item_not_found(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        updated = store.update_item("nonexistent_id", title="新标题")
        assert updated is None

    def test_update_item_reloads_correctly(self, tmp_path: Path) -> None:
        """更新后重新从磁盘读取应反映更改。"""
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        store.update_item("sp_001", priority=1, tags=["更新标签"])
        store2 = KnowledgeStore(tmp_path)
        items = store2.list_items(document_id="doc_001")
        sp = [i for i in items if i.id == "sp_001"][0]
        assert sp.priority == 1
        assert sp.tags == ["更新标签"]

    def test_get_top_selling_points_returns_by_priority(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        top = store.get_top_k_items(item_type="selling_point", k=2)
        assert len(top) == 2
        # Priorities: 5, 5, 4, 3 → top 2 should be the two 5s
        assert top[0].priority == 5
        assert top[1].priority == 5

    def test_get_top_selling_points_default_k(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate(store)
        top = store.get_top_k_items(item_type="selling_point")
        assert len(top) == 4  # default top_k=5 but only 4 selling points exist

    def test_get_top_selling_points_empty(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        assert store.get_top_k_items(item_type="selling_point") == []


class TestKnowledgeStoreRefresh:
    """Test refresh_all — re-extract from all documents."""

    def _populate_docs_and_items(self, store: KnowledgeStore) -> None:
        from packages.knowledge_store.models import KnowledgeDocument

        # Two documents with items
        doc1 = KnowledgeDocument(
            id="doc_001",
            filename="产品介绍.txt",
            source_type=SourceType.TXT,
            parsed_text="羊肚菌生长在云南高山中。",
        )
        doc2 = KnowledgeDocument(
            id="doc_002",
            filename="规格说明.txt",
            source_type=SourceType.TXT,
            parsed_text="每包500g，真空包装。",
        )
        store.save_document(doc1)
        store.save_document(doc2)
        items = [
            KnowledgeItem(
                id="old_001",
                document_id="doc_001",
                type=KnowledgeItemType.SELLING_POINT,
                title="旧卖点",
                content="旧内容",
                priority=3,
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="spec_001",
                document_id="doc_002",
                type=KnowledgeItemType.SPECIFICATION,
                title="旧规格",
                content="旧规格内容",
                priority=2,
                source_document="规格说明.txt",
            ),
        ]
        store.save_items(items)

    def test_refresh_all_removes_old_items_and_adds_new(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        self._populate_docs_and_items(store)

        # Verify old items exist
        assert len(store.list_items()) == 2

        # Create a mock extractor that returns new items
        class MockExtractor:
            def extract(self, text: str, source_document: str = ""):
                return [
                    KnowledgeItem(
                        id=f"new_{source_document}",
                        document_id="",
                        type=KnowledgeItemType.SELLING_POINT,
                        title="新卖点",
                        content=f"从{source_document}提取的新内容",
                        priority=5,
                        source_document=source_document,
                    )
                ]

        count = store.refresh_all(MockExtractor())
        # 2 documents * 1 item each = 2
        assert count == 2

        # Old items should be gone (cascade deleted)
        remaining = store.list_items()
        assert len(remaining) == 2
        for item in remaining:
            assert item.id != "old_001"
            assert item.id != "spec_001"

    def test_refresh_all_with_no_documents(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        count = store.refresh_all(None)
        assert count == 0

    def test_refresh_all_with_no_text(self, tmp_path: Path) -> None:
        from packages.knowledge_store.models import KnowledgeDocument

        store = KnowledgeStore(tmp_path)
        doc = KnowledgeDocument(
            id="doc_001",
            filename="empty.txt",
            source_type=SourceType.TXT,
            parsed_text="",
        )
        store.save_document(doc)

        class MockExtractor:
            def extract(self, text: str, source_document: str = ""):
                return []

        count = store.refresh_all(MockExtractor())
        assert count == 0
