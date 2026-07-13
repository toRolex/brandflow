from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.knowledge_store.models import KnowledgeItem, KnowledgeItemType


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
            files={"file": ("test.png", b"content")},
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


class TestKnowledgePDFUpload:
    """POST /api/knowledge/upload — PDF上传"""

    def _make_test_pdf(self, path: Path, text: str = "test pdf content") -> bytes:
        import fitz

        doc = fitz.open()
        page = doc.new_page()
        page.insert_htmlbox(
            fitz.Rect(50, 50, 500, 100),
            f"<p>{text}</p>",
        )
        doc.save(str(path))
        doc.close()
        return path.read_bytes()

    def test_upload_pdf_creates_document(self, tmp_path: Path) -> None:
        """上传PDF文件应返回文档ID"""
        pdf_bytes = self._make_test_pdf(tmp_path / "test.pdf")
        client = _client(tmp_path)

        with patch("apps.control_plane.routes.knowledge._make_extractor") as mock_maker:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = []
            mock_maker.return_value = mock_extractor
            resp = client.post(
                "/api/knowledge/upload",
                files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "document_id" in data
        assert data["filename"] == "test.pdf"
        assert "summary" in data

    def test_upload_pdf_with_extraction(self, tmp_path: Path) -> None:
        """上传PDF后，解析文本应进入LLM提取流水线"""
        pdf_bytes = self._make_test_pdf(
            tmp_path / "test.pdf", "羊肚菌是一种珍贵的食用菌"
        )
        client = _client(tmp_path)

        mock_item = KnowledgeItem(
            id="item_001",
            document_id="doc_001",
            type=KnowledgeItemType.SELLING_POINT,
            title="鲜美口感",
            content="羊肚菌口感鲜嫩",
            priority=5,
            tags=["口感"],
            source_document="test.pdf",
        )
        with patch("apps.control_plane.routes.knowledge._make_extractor") as mock_maker:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [mock_item]
            mock_maker.return_value = mock_extractor
            resp = client.post(
                "/api/knowledge/upload",
                files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] == 1
        assert "selling_point" in data["summary"]

    def test_upload_pdf_empty_file_returns_400(self, tmp_path: Path) -> None:
        """完全空的PDF文件（0字节）应返回400"""
        client = _client(tmp_path)
        resp = client.post(
            "/api/knowledge/upload",
            files={"file": ("empty.pdf", b"")},
        )
        assert resp.status_code == 400


class TestKnowledgeDocxUpload:
    """POST /api/knowledge/upload — DOCX上传"""

    def _make_test_docx(self, path: Path, text: str = "test docx content") -> bytes:
        from docx import Document

        doc = Document()
        doc.add_paragraph(text)
        doc.save(str(path))
        return path.read_bytes()

    def test_upload_docx_creates_document(self, tmp_path: Path) -> None:
        """上传DOCX文件应返回文档ID"""
        docx_bytes = self._make_test_docx(tmp_path / "test.docx")
        client = _client(tmp_path)

        with patch("apps.control_plane.routes.knowledge._make_extractor") as mock_maker:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = []
            mock_maker.return_value = mock_extractor
            resp = client.post(
                "/api/knowledge/upload",
                files={"file": ("test.docx", docx_bytes)},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "document_id" in data
        assert data["filename"] == "test.docx"

    def test_upload_docx_with_extraction(self, tmp_path: Path) -> None:
        """上传DOCX后，解析文本应进入LLM提取流水线"""
        docx_bytes = self._make_test_docx(tmp_path / "test.docx", "羊肚菌产品介绍")
        client = _client(tmp_path)

        mock_item = KnowledgeItem(
            id="item_002",
            document_id="doc_002",
            type=KnowledgeItemType.SPECIFICATION,
            title="规格",
            content="500g/包",
            priority=3,
            tags=["包装"],
            source_document="test.docx",
        )
        with patch("apps.control_plane.routes.knowledge._make_extractor") as mock_maker:
            mock_extractor = MagicMock()
            mock_extractor.extract.return_value = [mock_item]
            mock_maker.return_value = mock_extractor
            resp = client.post(
                "/api/knowledge/upload",
                files={"file": ("test.docx", docx_bytes)},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] == 1

    def test_upload_docx_empty_file_returns_400(self, tmp_path: Path) -> None:
        """完全空的DOCX文件（0字节）应返回400"""
        client = _client(tmp_path)
        resp = client.post(
            "/api/knowledge/upload",
            files={"file": ("empty.docx", b"")},
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
