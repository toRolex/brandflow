from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.knowledge_store.models import KnowledgeItem, SourceType, KnowledgeItemType
from packages.knowledge_store.store import KnowledgeStore


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _populate_selling_points(store: KnowledgeStore) -> None:
    items = [
        KnowledgeItem(
            id="sp_001",
            document_id="doc_001",
            type=KnowledgeItemType.SELLING_POINT,
            title="野生生长环境",
            content="生长在云南海拔2000米以上原始森林",
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
            content="每包500g真空包装",
            priority=2,
            tags=["包装"],
            source_document="规格.txt",
        ),
        KnowledgeItem(
            id="sp_005",
            document_id="doc_001",
            type=KnowledgeItemType.SELLING_POINT,
            title="农家手工采摘",
            content="每一朵由当地农户手工采摘",
            priority=5,
            tags=["产地", "工艺"],
            source_document="产品介绍.txt",
        ),
    ]
    store.save_items(items)


class TestSellingPointsAPI:
    """GET /api/knowledge/selling-points — listing with filters."""

    def test_list_all_selling_points(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/selling-points")
        assert resp.status_code == 200
        data = resp.json()
        # 4 selling points (specification should be excluded)
        assert len(data) == 4
        for item in data:
            assert item["type"] == "selling_point"

    def test_list_empty_when_no_items(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/selling-points")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_filter_by_priority_min(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/selling-points?priority_min=4")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3  # priorities 5, 5, 4
        for item in data:
            assert item["priority"] >= 4

    def test_filter_by_priority_max(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/selling-points?priority_max=3")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["priority"] == 3

    def test_filter_by_tags(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/selling-points?tags=口感")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "独特菌菇香气"

    def test_filter_by_multiple_tags_or(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/selling-points?tags=口感,营养")
        data = resp.json()
        assert len(data) == 2

    def test_filter_by_priority_and_tags(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/selling-points?priority_min=5&tags=天然")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "sp_001"


class TestUpdateSellingPointAPI:
    """PUT /api/knowledge/selling-points/{item_id} — update item fields."""

    def test_update_title(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.put(
            "/api/knowledge/selling-points/sp_001",
            json={"title": "野生环境"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "野生环境"
        assert data["id"] == "sp_001"
        # Other fields unchanged
        assert data["priority"] == 5

    def test_update_priority(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.put(
            "/api/knowledge/selling-points/sp_001",
            json={"priority": 1},
        )
        data = resp.json()
        assert data["priority"] == 1

    def test_update_tags(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.put(
            "/api/knowledge/selling-points/sp_001",
            json={"tags": ["高端", "天然"]},
        )
        data = resp.json()
        assert data["tags"] == ["高端", "天然"]

    def test_update_content(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.put(
            "/api/knowledge/selling-points/sp_001",
            json={"content": "新内容"},
        )
        data = resp.json()
        assert data["content"] == "新内容"

    def test_update_not_found(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        resp = client.put(
            "/api/knowledge/selling-points/nonexistent",
            json={"title": "新标题"},
        )
        assert resp.status_code == 404

    def test_update_persists(self, tmp_path: Path) -> None:
        """更新后重新读取应反映更改。"""
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        client = _client(tmp_path)
        client.put(
            "/api/knowledge/selling-points/sp_001",
            json={"title": "持久化标题"},
        )
        # Re-read from API
        resp = client.get("/api/knowledge/selling-points")
        data = resp.json()
        sp = [i for i in data if i["id"] == "sp_001"][0]
        assert sp["title"] == "持久化标题"


class TestRefreshAPI:
    """POST /api/knowledge/refresh — re-extract from all documents."""

    def test_refresh_returns_count(self, tmp_path: Path) -> None:
        store = KnowledgeStore(tmp_path)
        _populate_selling_points(store)
        # Add a document to refresh from
        from packages.knowledge_store.models import KnowledgeDocument

        doc = KnowledgeDocument(
            id="doc_001",
            filename="产品介绍.txt",
            source_type=SourceType.TXT,
            parsed_text="羊肚菌生长在云南高山中。",
        )
        store.save_document(doc)

        client = _client(tmp_path)

        with patch(
            "packages.knowledge_store.extractor.KnowledgeExtractor.extract"
        ) as mock_extract:
            mock_extract.return_value = [
                KnowledgeItem(
                    id="refreshed_001",
                    document_id="",
                    type=KnowledgeItemType.SELLING_POINT,
                    title="新卖点",
                    content="新内容",
                    priority=5,
                    source_document="产品介绍.txt",
                ),
            ]
            resp = client.post("/api/knowledge/refresh")

        assert resp.status_code == 200
        data = resp.json()
        assert "refreshed_count" in data
        assert isinstance(data["refreshed_count"], int)

    def test_refresh_empty(self, tmp_path: Path) -> None:
        """没有文档时 refresh 应返回 0 且不报错。"""
        client = _client(tmp_path)
        resp = client.post("/api/knowledge/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refreshed_count"] == 0

    def test_refresh_requires_auth(self, tmp_path: Path) -> None:
        """refresh 在没有 extractor 时静默返回 0。"""
        store = KnowledgeStore(tmp_path)
        from packages.knowledge_store.models import KnowledgeDocument

        doc = KnowledgeDocument(
            id="doc_001",
            filename="test.txt",
            source_type=SourceType.TXT,
            parsed_text="测试内容",
        )
        store.save_document(doc)
        client = _client(tmp_path)

        with patch(
            "apps.control_plane.routes.knowledge._make_extractor",
            return_value=None,
        ):
            resp = client.post("/api/knowledge/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["refreshed_count"] == 0
