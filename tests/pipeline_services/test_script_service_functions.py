from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from packages.pipeline_services.script_service import (
    generate_cover_title,
    generate_script,
)


def _make_config_mocks(product: str = ""):
    reader = MagicMock()
    reader.get_llm_config.return_value = {"model": "deepseek-v4-pro", "provider": "deepseek"}
    secrets = MagicMock()
    secrets.get_api_key.return_value = "fake-api-key"
    secrets.get_api_base_url.return_value = "https://api.example.com/v1"
    return reader, secrets


@patch("packages.pipeline_services.script_service.generator.validate_script")
@patch("packages.pipeline_services.script_service.generator.ScriptGenerator._call_llm")
class TestGenerateScript:
    def test_writes_txt_and_json_and_returns_dict(
        self, mock_call_llm, mock_validate, tmp_path: Path
    ):
        mock_validate.return_value = {"ok": True, "errors": []}
        mock_call_llm.side_effect = [
            json.dumps(
                {
                    "sentence_1": "云南深山里藏着一种宝贝。",
                    "sentence_2": "它就是鲜嫩的羊肚菌。",
                    "sentence_3": "采摘后立刻送到你手中。",
                    "sentence_4": "今天教大家怎么做好吃。",
                },
                ensure_ascii=False,
            ),
            json.dumps(
                {
                    "sentence_5": "锅里放油烧热下菌子。",
                    "sentence_6": "充分烹熟才能安心享用。",
                    "sentence_7": "滋元堂的品质值得信赖。",
                    "sentence_8": "赶紧下单尝尝吧。",
                },
                ensure_ascii=False,
            ),
        ]

        reader, secrets = _make_config_mocks()
        result = generate_script(
            product="羊肚菌",
            output_dir=tmp_path,
            language="mandarin",
            brand="滋元堂",
            config_reader=reader,
            secret_store=secrets,
        )

        txt_path = tmp_path / "口播文案.txt"
        json_path = tmp_path / "口播文案.json"
        assert txt_path.exists()
        assert json_path.exists()
        assert result["txt_path"] == str(txt_path)
        assert result["json_path"] == str(json_path)
        assert "羊肚菌" in result["final_script"]
        assert "滋元堂" in result["final_script"]

        jdata = json.loads(json_path.read_text(encoding="utf-8"))
        assert jdata["product"] == "羊肚菌"
        assert jdata["brand"] == "滋元堂"
        assert jdata["language"] == "mandarin"
        assert jdata["final_script"] == result["final_script"]

    def test_uses_config_resolver_llm(
        self, mock_call_llm, mock_validate, tmp_path: Path
    ):
        mock_validate.return_value = {"ok": True, "errors": []}
        mock_call_llm.side_effect = [
            json.dumps({"sentence_1": "第一句。"}, ensure_ascii=False),
            json.dumps({"sentence_2": "第二句。"}, ensure_ascii=False),
        ]

        reader, secrets = _make_config_mocks()
        generate_script(
            product="测试",
            output_dir=tmp_path,
            language="mandarin",
            brand="",
            config_reader=reader,
            secret_store=secrets,
        )

        reader.get_llm_config.assert_called_once_with(product_id="测试")
        secrets.get_api_key.assert_called_once_with("deepseek")


@patch("packages.pipeline_services.script_service.generator.ScriptGenerator._call_llm")
class TestGenerateCoverTitle:
    def test_returns_title_dict(self, mock_call_llm, tmp_path: Path):
        mock_call_llm.return_value = json.dumps(
            {"title": "羊肚菌美味推荐", "highlight_words": ["羊肚菌", "美味"]},
            ensure_ascii=False,
        )

        reader, secrets = _make_config_mocks()
        result = generate_cover_title(
            script_text="今天给大家介绍羊肚菌的做法，滋元堂品质保证。",
            product="羊肚菌",
            brand="滋元堂",
            config_reader=reader,
            secret_store=secrets,
        )

        assert result["text"] == "羊肚菌美味推荐"
        assert result["highlight_words"] == ["羊肚菌", "美味"]

    def test_uses_config_resolver_llm(self, mock_call_llm, tmp_path: Path):
        mock_call_llm.return_value = json.dumps(
            {"title": "标题", "highlight_words": []}, ensure_ascii=False
        )

        reader, secrets = _make_config_mocks()
        generate_cover_title(
            script_text="测试文案。",
            product="测试",
            brand="",
            config_reader=reader,
            secret_store=secrets,
        )

        reader.get_llm_config.assert_called_once_with(product_id="测试")
        secrets.get_api_key.assert_called_once_with("deepseek")
