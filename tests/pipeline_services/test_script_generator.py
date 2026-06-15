from __future__ import annotations

import pytest

from packages.pipeline_services.script_service.quality import validate_script


class TestValidateScript:
    def test_valid_script_passes(self):
        text = "今天给大家介绍一种美味食材。" * 11 + "滋元堂的羊肚菌来自云南深山，充分烹熟后口感鲜美，营养丰富。"
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True
        assert result["errors"] == []

    def test_too_short_rejected(self):
        text = "太短了。"
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("字数" in e for e in result["errors"])

    def test_too_long_rejected(self):
        text = "这是一个很长的文本。" * 30
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("字数" in e for e in result["errors"])

    def test_missing_product_rejected(self):
        text = "今天介绍一种美味食材的做法。滋元堂的产品来自云南深山，充分烹熟后口感非常好，推荐大家尝试。" * 3
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("品名" in e for e in result["errors"])

    def test_missing_brand_rejected(self):
        text = "今天介绍羊肚菌的做法。这种食材来自云南深山，充分烹熟后口感非常好，推荐大家尝试购买品尝。" * 3
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("品牌" in e or "滋元堂" in e for e in result["errors"])

    def test_missing_cook_thoroughly_rejected(self):
        text = "今天介绍羊肚菌的做法。滋元堂的产品来自云南深山，口感非常好，推荐大家尝试购买品尝享用。" * 3
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("充分烹熟" in e for e in result["errors"])

    def test_emoji_rejected(self):
        text = "今天介绍羊肚菌的做法😊。滋元堂的产品来自云南深山，充分烹熟后口感非常好，推荐大家尝试购买品尝。" * 3
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("emoji" in e.lower() or "表情" in e for e in result["errors"])

    def test_medical_terms_rejected(self):
        text = "今天介绍羊肚菌的做法。滋元堂的产品可以治疗疾病，充分烹熟后口感非常好，推荐大家尝试购买品尝。" * 3
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("医疗" in e or "禁词" in e for e in result["errors"])

    def test_brand_appearing_twice_rejected(self):
        text = "滋元堂今天介绍羊肚菌的做法。滋元堂滋元堂的产品来自云南深山，充分烹熟后口感非常好，推荐尝试。" * 3
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("品牌" in e and "次" in e for e in result["errors"])


from packages.pipeline_services.script_service.prompts import (
    build_first_half_messages,
    build_second_half_messages,
)


class TestPromptConstruction:
    def test_first_half_contains_product_and_brand(self):
        messages = build_first_half_messages(
            product="羊肚菌",
            brand="滋元堂",
            scene="云南山野",
            material="菌子近景",
        )
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        user_content = messages[1]["content"]
        assert "羊肚菌" in user_content
        assert "滋元堂" in user_content

    def test_second_half_contains_first_half(self):
        messages = build_second_half_messages(
            product="羊肚菌",
            brand="滋元堂",
            scene="云南山野",
            material="菌子近景",
            first_half="前半段测试文本内容。",
            first_length=8,
        )
        user_content = messages[-1]["content"]
        assert "前半段测试文本内容" in user_content


import json
from unittest.mock import MagicMock, patch

from packages.pipeline_services.script_service.generator import ScriptGenerator, ScriptResult


class TestScriptGenerator:
    def _make_generator(self):
        config = MagicMock()
        config.api_key = "test-key"
        config.base_url = "https://api.deepseek.com/v1"
        config.model = "deepseek-v4-pro"
        return ScriptGenerator(config)

    @patch.object(ScriptGenerator, "_call_llm")
    def test_generate_returns_script_result(self, mock_call_llm):
        first_json = json.dumps({
            "sentence_1": "云南深山里藏着一种宝贝。",
            "sentence_2": "它就是鲜嫩的羊肚菌。",
            "sentence_3": "采摘后立刻送到你手中。",
            "sentence_4": "今天教大家怎么做好吃。",
        }, ensure_ascii=False)
        second_json = json.dumps({
            "sentence_5": "锅里放油烧热下菌子。",
            "sentence_6": "充分烹熟才能安心享用。",
            "sentence_7": "滋元堂的品质值得信赖。",
            "sentence_8": "赶紧下单尝尝吧。",
        }, ensure_ascii=False)
        mock_call_llm.side_effect = [first_json, second_json] * 3

        gen = self._make_generator()
        result = gen.run(product="羊肚菌", brand="滋元堂", mock=False)

        assert isinstance(result, ScriptResult)
        assert len(result.full_text) > 0
        assert "羊肚菌" in result.full_text
        assert "滋元堂" in result.full_text
        assert "充分烹熟" in result.full_text

    def test_generate_mock_returns_stub(self):
        gen = self._make_generator()
        result = gen.run(product="羊肚菌", brand="滋元堂", mock=True)

        assert isinstance(result, ScriptResult)
        assert result.mock is True
        assert "羊肚菌" in result.full_text
