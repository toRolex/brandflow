from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
from docx import Document
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.script_service.generator import (
    ScriptGenerator,
    ScriptResult,
)


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _make_test_pdf(path: Path, text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_htmlbox(fitz.Rect(50, 50, 500, 100), f"<p>{text}</p>")
    doc.save(str(path))
    doc.close()
    return path.read_bytes()


def _make_test_docx(path: Path, text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(str(path))
    return path.read_bytes()


def _extraction_llm_response() -> str:
    return json.dumps(
        {
            "items": [
                {
                    "type": "selling_point",
                    "title": "鲜美口感",
                    "content": "羊肚菌口感鲜嫩，营养丰富",
                    "priority": 5,
                    "tags": ["口感"],
                },
                {
                    "type": "specification",
                    "title": "产地",
                    "content": "云南高山",
                    "priority": 3,
                    "tags": ["产地"],
                },
            ]
        },
        ensure_ascii=False,
    )


class TestPdfWordEndToEndIntegration:
    """End-to-end: upload PDF/DOCX → extract items → inject into script generation."""

    def _patch_extractor_deps(self):
        """Patch app config and LLM client so extraction runs without real keys."""
        return patch.multiple(
            "packages.provider_config.app_config.AppConfigManager",
            get_llm_api_key=MagicMock(return_value="test-key"),
            get_llm_endpoint=MagicMock(return_value="https://api.test/v1"),
            get_llm_config=MagicMock(return_value={"model": "test-model"}),
        )

    @patch.object(ScriptGenerator, "_call_llm")
    def test_upload_pdf_then_script_injection(
        self, mock_script_call_llm, tmp_path: Path
    ) -> None:
        """上传 PDF → LLM 提取 → items 被 ScriptGenerator 消费。"""
        pdf_bytes = _make_test_pdf(
            tmp_path / "test.pdf", "羊肚菌是一种珍贵的食用菌，口感鲜嫩。"
        )
        client = _client(tmp_path)

        with self._patch_extractor_deps():
            with patch(
                "packages.pipeline_services.llm_client.LLMClient.chat"
            ) as mock_chat:
                mock_chat.return_value = _extraction_llm_response()
                resp = client.post(
                    "/api/knowledge/upload",
                    files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] == 2
        assert data["summary"].get("selling_point", 0) >= 1

        # Verify items are persisted and injectable into script generation
        first_json = json.dumps(
            {
                "sentence_1": "云南深山里藏着一种宝贝。",
                "sentence_2": "它就是鲜嫩的羊肚菌。",
                "sentence_3": "采摘后立刻送到你手中。",
                "sentence_4": "今天教大家怎么做好吃。",
            },
            ensure_ascii=False,
        )
        second_json = json.dumps(
            {
                "sentence_5": "锅里放油烧热下菌子。",
                "sentence_6": "充分烹熟才能安心享用。",
                "sentence_7": "滋元堂的品质值得信赖。",
                "sentence_8": "赶紧下单尝尝吧。",
            },
            ensure_ascii=False,
        )
        mock_script_call_llm.side_effect = [first_json, second_json] * 3

        config = MagicMock()
        config.api_key = "test-key"
        config.base_url = "https://api.test/v1"
        config.model = "test-model"
        gen = ScriptGenerator(config)
        result = gen.run(
            product="羊肚菌",
            brand="滋元堂",
            knowledge_config={
                "enabled": True,
                "store_dir": str(tmp_path),
                "top_k": 5,
            },
        )

        assert isinstance(result, ScriptResult)
        assert result.full_text != ""

        # Selling point extracted from PDF should appear in system prompt
        first_call_messages = mock_script_call_llm.call_args_list[0][0][0]
        system_content = first_call_messages[0]["content"]
        assert "鲜美口感" in system_content
        assert "羊肚菌口感鲜嫩" in system_content

    @patch.object(ScriptGenerator, "_call_llm")
    def test_upload_docx_then_script_injection(
        self, mock_script_call_llm, tmp_path: Path
    ) -> None:
        """上传 DOCX → LLM 提取 → items 被 ScriptGenerator 消费。"""
        docx_bytes = _make_test_docx(
            tmp_path / "test.docx", "羊肚菌产自云南高山，营养丰富。"
        )
        client = _client(tmp_path)

        with self._patch_extractor_deps():
            with patch(
                "packages.pipeline_services.llm_client.LLMClient.chat"
            ) as mock_chat:
                mock_chat.return_value = _extraction_llm_response()
                resp = client.post(
                    "/api/knowledge/upload",
                    files={
                        "file": (
                            "test.docx",
                            docx_bytes,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["item_count"] == 2
        assert data["summary"].get("selling_point", 0) >= 1

        first_json = json.dumps(
            {
                "sentence_1": "云南深山里藏着一种宝贝。",
                "sentence_2": "它就是鲜嫩的羊肚菌。",
                "sentence_3": "采摘后立刻送到你手中。",
                "sentence_4": "今天教大家怎么做好吃。",
            },
            ensure_ascii=False,
        )
        second_json = json.dumps(
            {
                "sentence_5": "锅里放油烧热下菌子。",
                "sentence_6": "充分烹熟才能安心享用。",
                "sentence_7": "滋元堂的品质值得信赖。",
                "sentence_8": "赶紧下单尝尝吧。",
            },
            ensure_ascii=False,
        )
        mock_script_call_llm.side_effect = [first_json, second_json] * 3

        config = MagicMock()
        config.api_key = "test-key"
        config.base_url = "https://api.test/v1"
        config.model = "test-model"
        gen = ScriptGenerator(config)
        result = gen.run(
            product="羊肚菌",
            brand="滋元堂",
            knowledge_config={
                "enabled": True,
                "store_dir": str(tmp_path),
                "top_k": 5,
            },
        )

        assert isinstance(result, ScriptResult)
        assert result.full_text != ""

        first_call_messages = mock_script_call_llm.call_args_list[0][0][0]
        system_content = first_call_messages[0]["content"]
        assert "鲜美口感" in system_content


class TestMimeTypeDetection:
    """Upload route should detect file type from MIME type, not only extension."""

    def test_upload_pdf_with_unknown_extension_uses_mime_type(
        self, tmp_path: Path
    ) -> None:
        """文件扩展名异常但 MIME type 正确时，应正确解析为 PDF。"""
        pdf_bytes = _make_test_pdf(tmp_path / "test.bin", "羊肚菌珍贵食用菌")
        client = _client(tmp_path)

        with patch.multiple(
            "packages.provider_config.app_config.AppConfigManager",
            get_llm_api_key=MagicMock(return_value="test-key"),
            get_llm_endpoint=MagicMock(return_value="https://api.test/v1"),
            get_llm_config=MagicMock(return_value={"model": "test-model"}),
        ):
            with patch(
                "packages.pipeline_services.llm_client.LLMClient.chat"
            ) as mock_chat:
                mock_chat.return_value = json.dumps(
                    {"items": []}, ensure_ascii=False
                )
                resp = client.post(
                    "/api/knowledge/upload",
                    files={"file": ("test.bin", pdf_bytes, "application/pdf")},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "test.bin"

    def test_upload_docx_with_unknown_extension_uses_mime_type(
        self, tmp_path: Path
    ) -> None:
        """文件扩展名异常但 MIME type 正确时，应正确解析为 DOCX。"""
        docx_bytes = _make_test_docx(tmp_path / "test.bin", "羊肚菌产自云南")
        client = _client(tmp_path)

        with patch.multiple(
            "packages.provider_config.app_config.AppConfigManager",
            get_llm_api_key=MagicMock(return_value="test-key"),
            get_llm_endpoint=MagicMock(return_value="https://api.test/v1"),
            get_llm_config=MagicMock(return_value={"model": "test-model"}),
        ):
            with patch(
                "packages.pipeline_services.llm_client.LLMClient.chat"
            ) as mock_chat:
                mock_chat.return_value = json.dumps(
                    {"items": []}, ensure_ascii=False
                )
                resp = client.post(
                    "/api/knowledge/upload",
                    files={
                        "file": (
                            "test.bin",
                            docx_bytes,
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        )
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["filename"] == "test.bin"
