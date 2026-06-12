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
