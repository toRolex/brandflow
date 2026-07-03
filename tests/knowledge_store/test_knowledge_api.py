from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


_TXT_CONTENT = "test product content for knowledge extraction."


class TestKnowledgeAPI:
    """POST /api/knowledge/upload — TXT上传 + LLM提取"""

    def test_upload_txt_creates_document(self, tmp_path: Path) -> None:
        """上传TXT文件应返回文档ID"""
        client = _client(tmp_path)

        with patch(
            "packages.knowledge_store.extractor.KnowledgeExtractor.extract"
        ) as mock_extract:
            mock_extract.return_value = []
            resp = client.post(
                "/api/knowledge/upload",
                files={"file": ("test.txt", _TXT_CONTENT)},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "document_id" in data
        assert data["filename"] == "test.txt"
        assert "summary" in data

    def test_upload_invalid_extension(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post(
            "/api/knowledge/upload",
            files={"file": ("test.pdf", b"content")},
        )
        assert resp.status_code == 400

    def test_upload_no_file(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post("/api/knowledge/upload")
        assert resp.status_code == 422  # FastAPI validation error

    def test_upload_empty_file(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.post(
            "/api/knowledge/upload",
            files={"file": ("empty.txt", b"")},
        )
        assert resp.status_code == 400


class TestKnowledgeListDocuments:
    """GET /api/knowledge/documents — 列出文档"""

    def test_list_empty(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_upload(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        with patch(
            "packages.knowledge_store.extractor.KnowledgeExtractor.extract"
        ) as mock_extract:
            mock_extract.return_value = []
            client.post(
                "/api/knowledge/upload",
                files={"file": ("test.txt", _TXT_CONTENT)},
            )
        resp = client.get("/api/knowledge/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["filename"] == "test.txt"
        assert "id" in data[0]
        assert "created_at" in data[0]


class TestKnowledgeGetItems:
    """GET /api/knowledge/documents/{id}/items — 查询提取结果"""

    def test_get_items_for_document(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        with patch(
            "packages.knowledge_store.extractor.KnowledgeExtractor.extract"
        ) as mock_extract:
            mock_extract.return_value = []
            upload_resp = client.post(
                "/api/knowledge/upload",
                files={"file": ("test.txt", _TXT_CONTENT)},
            )
        doc_id = upload_resp.json()["document_id"]
        resp = client.get(f"/api/knowledge/documents/{doc_id}/items")
        assert resp.status_code == 200

    def test_get_items_not_found(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        resp = client.get("/api/knowledge/documents/nonexistent/items")
        assert resp.status_code == 404
