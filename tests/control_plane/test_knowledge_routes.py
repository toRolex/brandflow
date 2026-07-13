from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.knowledge_store.extractor import KnowledgeExtractor
from packages.pipeline_services.script_service.generator import (
    ScriptGenerator,
    ScriptResult,
)

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


class TestKnowledgeUploadLimits:
    """POST /api/knowledge/upload file size guards."""

    def test_upload_txt_rejects_files_over_20mb(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        big_content = b"x" * (MAX_FILE_SIZE_BYTES + 1)
        resp = client.post(
            "/api/knowledge/upload",
            files={"file": ("big.txt", big_content)},
        )
        assert resp.status_code == 413
        assert "20MB" in resp.json()["detail"]


class TestKnowledgeUploadExtractGenerate:
    """Integration: TXT upload -> LLM extraction -> ScriptGenerator injection."""

    def _make_extractor(self) -> KnowledgeExtractor:
        mock_client = MagicMock()
        mock_client.chat.return_value = json.dumps(
            {
                "items": [
                    {
                        "type": "selling_point",
                        "title": "野生生长环境",
                        "content": "生长在云南海拔2000米以上原始森林中",
                        "priority": 5,
                        "tags": ["产地"],
                    }
                ]
            },
            ensure_ascii=False,
        )
        return KnowledgeExtractor(llm_client=mock_client)

    def test_upload_txt_extracts_and_injects_into_script(self, tmp_path: Path) -> None:
        client = _client(tmp_path)
        extractor = self._make_extractor()

        with patch(
            "apps.control_plane.routes.knowledge._make_extractor",
            return_value=extractor,
        ):
            upload_resp = client.post(
                "/api/knowledge/upload",
                files={
                    "file": (
                        "product.txt",
                        "羊肚菌生长在云南高山原始森林中，天然无污染。",
                    )
                },
            )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        assert upload_data["item_count"] == 1
        assert "selling_point" in upload_data["summary"]
        doc_id = upload_data["document_id"]

        # Verify items are queryable
        items_resp = client.get(f"/api/knowledge/documents/{doc_id}/items")
        assert items_resp.status_code == 200
        items = items_resp.json()
        assert len(items) == 1
        assert items[0]["title"] == "野生生长环境"

        # Generate script using the same knowledge store
        config = MagicMock()
        config.api_key = "test-key"
        config.base_url = "https://api.deepseek.com/v1"
        config.model = "deepseek-v4-pro"
        gen = ScriptGenerator(config)

        first_json = json.dumps(
            {
                "sentence_1": "生长在云南海拔2000米以上原始森林中的羊肚菌，朵大肉厚品质上乘。",
                "sentence_2": "当地农户手工采摘，精挑细选后直达厨房，保证新鲜完整。",
                "sentence_3": "口感鲜嫩爽滑，菌香浓郁，炖汤炒菜都让人回味无穷。",
                "sentence_4": "今天用最简单的方法，教你做一道营养美味的家常菜。",
            },
            ensure_ascii=False,
        )
        second_json = json.dumps(
            {
                "sentence_5": "锅里放少许油烧热，倒入食材大火翻炒出香味。",
                "sentence_6": "记得充分烹熟，才能安心享用这份山野珍贵馈赠。",
                "sentence_7": "品质经得起考验，家人吃得放心，才是最重要的事。",
                "sentence_8": "现在下单，新鲜好食材很快就能送到手中，赶紧尝尝吧。",
            },
            ensure_ascii=False,
        )

        with patch.object(gen, "_call_llm") as mock_call_llm:
            mock_call_llm.side_effect = [first_json, second_json] * 3
            result = gen.run(
                product="羊肚菌",
                brand="",
                knowledge_config={
                    "enabled": True,
                    "store_dir": str(tmp_path),
                    "top_k": 3,
                },
            )

        assert isinstance(result, ScriptResult)
        assert result.quality["ok"] is True, result.quality["errors"]
        assert "海拔2000米以上原始森林" in result.full_text

        # Verify the selling point was injected into the system prompt
        call_args_list = mock_call_llm.call_args_list
        assert len(call_args_list) >= 2
        system_content = call_args_list[0][0][0][0]["content"]
        assert "野生生长环境" in system_content
        assert "生长在云南海拔2000米以上原始森林中" in system_content

        # Second half also receives the knowledge prompt
        second_system = call_args_list[1][0][0][0]["content"]
        assert "野生生长环境" in second_system
