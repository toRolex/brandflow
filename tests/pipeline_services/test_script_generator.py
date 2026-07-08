from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from packages.pipeline_services.script_service.generator import (
    ScriptGenerator,
    ScriptResult,
)
from packages.pipeline_services.script_service.prompts import (
    build_first_half_messages,
    build_second_half_messages,
    build_cantonese_conversion_messages,
)
from packages.pipeline_services.script_service.quality import (
    validate_script,
    validate_cantonese_script,
)


class TestValidateScript:
    def test_valid_script_passes(self):
        text = (
            "今天给大家介绍一种美味食材。" * 11
            + "滋元堂的羊肚菌来自云南深山，充分烹熟后口感鲜美，营养丰富。"
        )
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
        text = (
            "今天介绍一种美味食材的做法。滋元堂的产品来自云南深山，充分烹熟后口感非常好，推荐大家尝试。"
            * 3
        )
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("品名" in e for e in result["errors"])

    def test_missing_brand_rejected(self):
        text = (
            "今天介绍羊肚菌的做法。这种食材来自云南深山，充分烹熟后口感非常好，推荐大家尝试购买品尝。"
            * 3
        )
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("品牌" in e or "滋元堂" in e for e in result["errors"])

    def test_missing_cook_thoroughly_no_longer_rejected(self):
        """充分烹熟检查已移除——不含充分烹熟的脚本不再被拒稿。"""
        text = (
            "羊肚菌是滋元堂的一款精选食材口感鲜嫩营养丰富烹饪时需注意火候掌握"
            "做熟后即可安心享用今天为大家介绍这款产品的家常做法简单易学味道好"
            "挑选优质原料用心烹制每一口都是自然的鲜美滋味家庭厨房也能轻松上手"
            "让餐桌多一道健康美味选择日常烹饪建议搭配清淡调味保留食材原本鲜香"
            "喜爱美食的朋友千万不要错过这款来自大自然的馈赠让全家人共享鲜美"
            "菌菇做法多样可炒可炖可煲汤每一种都有独特风味值得一试"
            "今天就把这份健康带给家人吧"
        )
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True

    def test_emoji_rejected(self):
        text = (
            "今天介绍羊肚菌的做法😊。滋元堂的产品来自云南深山，充分烹熟后口感非常好，推荐大家尝试购买品尝。"
            * 3
        )
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("emoji" in e.lower() or "表情" in e for e in result["errors"])

    def test_medical_terms_rejected(self):
        text = (
            "今天介绍羊肚菌的做法。滋元堂的产品可以治疗疾病，充分烹熟后口感非常好，推荐大家尝试购买品尝。"
            * 3
        )
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("医疗" in e or "禁词" in e for e in result["errors"])

    def test_brand_appearing_twice_rejected(self):
        text = (
            "滋元堂今天介绍羊肚菌的做法。滋元堂滋元堂的产品来自云南深山，充分烹熟后口感非常好，推荐尝试。"
            * 3
        )
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("品牌" in e and "次" in e for e in result["errors"])


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


class TestScriptGenerator:
    def _make_generator(self):
        config = MagicMock()
        config.api_key = "test-key"
        config.base_url = "https://api.deepseek.com/v1"
        config.model = "deepseek-v4-pro"
        return ScriptGenerator(config)

    @patch.object(ScriptGenerator, "_call_llm")
    def test_generate_returns_script_result(self, mock_call_llm):
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


class TestValidateCantoneseScript:
    def test_valid_cantonese_passes(self):
        text = (
            "今日同大家介紹一種美味食材。" * 11
            + "滋元堂嘅羊肚菌嚟自雲南深山，徹底煮熟之後口感好正，營養豐富。"
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True
        assert result["errors"] == []

    def test_too_short_rejected(self):
        text = "太短。"
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("字数" in e for e in result["errors"])

    def test_too_long_rejected(self):
        text = "呢個係一個好長嘅文本。" * 30
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("字数" in e for e in result["errors"])

    def test_missing_product_rejected(self):
        text = (
            "今日介紹一種美味食材嘅做法。滋元堂嘅產品嚟自雲南深山，徹底煮熟之後口感好正，推薦大家嘗試。"
            * 3
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("品名" in e for e in result["errors"])

    def test_missing_brand_rejected(self):
        text = (
            "今日介紹羊肚菌嘅做法。呢種食材嚟自雲南深山，徹底煮熟之後口感好正，推薦大家嘗試購買品嚐。"
            * 3
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("品牌" in e for e in result["errors"])

    def test_missing_cook_term_no_longer_rejected(self):
        """粤语烹熟检查已移除——不含烹熟同义词的脚本不再被拒稿。"""
        text = (
            "今日介紹羊肚菌嘅做法滋元堂嘅產品嚟自雲南深山口感好正"
            "推薦大家嘗試購買品嚐享用呢款食材營養價值高適合日常煲湯燉煮"
            "鍾意食菌嘅朋友千祈唔好錯過羊肚菌嘅獨特香氣令人一試難忘"
            "無論係炒定係燉湯都好滋味加啲肉片一齊煮味道更加豐富"
            "鐘意自己煮嘢食嘅朋友一定要試下呢款食材保證你食過返尋味"
            "簡單幾步就可以煮出餐廳級別嘅美食唔使好複雜嘅技巧都可以做到"
            "今日就試下為屋企人煮一餐好味嘅羊肚菌啦"
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True

    def test_cantonese_cook_synonym_accepted(self):
        text = (
            "今日介紹羊肚菌嘅做法。" * 12
            + "滋元堂嘅產品嚟自雲南深山，煮到熟透之後口感好正，推薦大家嘗試購買。"
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True

    def test_emoji_rejected(self):
        text = (
            "今日介紹羊肚菌嘅做法😊。滋元堂嘅產品嚟自雲南深山，徹底煮熟之後口感好正，推薦大家嘗試購買品嚐。"
            * 3
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("emoji" in e.lower() or "表情" in e for e in result["errors"])

    def test_medical_terms_rejected(self):
        # Medical terms should be caught even when length is valid
        text = (
            "今日介紹羊肚菌嘅做法。滋元堂嘅產品可以治療疾病，徹底煮熟之後口感好正。" * 4
            + "推薦大家嘗試購買品嚐。"
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is False
        assert any("医疗" in e or "禁词" in e for e in result["errors"])

    def test_brand_multiple_occurrences_accepted(self):
        """粤语版不要求品牌恰好出现1次，出现多次也接受。"""
        text = (
            "滋元堂今日介紹羊肚菌嘅做法。滋元堂嘅產品嚟自雲南深山，徹底煮熟之後口感好正。"
            * 5
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True

    def test_product_multiple_occurrences_accepted(self):
        """粤语版不要求品名恰好出现1次，出现多次也接受。"""
        text = (
            "羊肚菌係一種美味食材。羊肚菌嚟自雲南深山，滋元堂嘅品質值得信賴，徹底煮熟之後先食得安心。"
            * 4
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True


class TestCantonesePromptConstruction:
    def test_conversion_messages_contain_product_and_brand(self):
        messages = build_cantonese_conversion_messages(
            mandarin_text="今天介绍羊肚菌的做法。滋元堂的产品来自云南深山，充分烹熟后口感很好。",
            product="羊肚菌",
            brand="滋元堂",
        )
        assert len(messages) >= 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        user_content = messages[1]["content"]
        assert "羊肚菌" in user_content
        assert "滋元堂" in user_content
        assert "充分烹熟" in user_content

    def test_conversion_system_prompt_uses_cantonese_terms(self):
        messages = build_cantonese_conversion_messages(
            mandarin_text="测试文案内容。",
            product="羊肚菌",
            brand="滋元堂",
        )
        system = messages[0]["content"]
        assert "粤语" in system
        # 充分烹熟/烹熟同义词已从 system prompt 中移除
        assert "不使用emoji" in system
        assert "不提及医疗功效" in system


class TestScriptGeneratorCantonese:
    def _make_generator(self):
        config = MagicMock()
        config.api_key = "test-key"
        config.base_url = "https://api.deepseek.com/v1"
        config.model = "deepseek-v4-pro"
        return ScriptGenerator(config)

    @patch.object(ScriptGenerator, "_call_llm")
    def test_to_cantonese_calls_llm(self, mock_call_llm):
        mock_call_llm.return_value = "今日同大家介紹羊肚菌嘅做法。滋元堂嘅產品嚟自雲南深山，徹底煮熟之後口感好正。"
        gen = self._make_generator()
        result = gen.to_cantonese(
            "今天介绍羊肚菌的做法。滋元堂的产品来自云南深山，充分烹熟后口感很好。",
            "羊肚菌",
            "滋元堂",
        )
        assert mock_call_llm.called
        assert "徹底煮熟" in result or "煮熟" in result

    @patch.object(ScriptGenerator, "_call_llm")
    def test_run_cantonese_returns_cantonese_text(self, mock_call_llm):
        # Each sentence ~20+ chars to reach 150+ compact_len across 8 sentences
        first_json = json.dumps(
            {
                "sentence_1": "云南深山里面藏着一种鲜嫩美味的羊肚菌宝贝。",
                "sentence_2": "它生长在高海拔无污染的山林之中静静等待。",
                "sentence_3": "采摘后立刻送到你手中保证绝对新鲜不流失。",
                "sentence_4": "今天教大家怎么做既营养丰富又好吃的美味。",
            },
            ensure_ascii=False,
        )
        second_json = json.dumps(
            {
                "sentence_5": "锅里放油烧热下菌子翻炒香气四溢满屋子。",
                "sentence_6": "充分烹熟才能安心享用这鲜美无比的好菌子。",
                "sentence_7": "滋元堂的品质值得信赖放心大胆购买和品尝。",
                "sentence_8": "赶紧下单品尝这云南深山里面的美味佳肴吧。",
            },
            ensure_ascii=False,
        )
        # Long enough to pass 150-char Cantonese QA
        cantonese_text = (
            "雲南深山裡邊藏住一種寶貝，就係鮮嫩嘅羊肚菌，採摘之後即刻送到你手中，今日教大家點樣煮先好食。"
            "鑊度落油燒熱落菌子，徹底煮熟先至可以安心享用，滋元堂嘅品質值得信賴，快啲落單試下啦。"
            "呢個產品真係好正，大家試過都話好味，唔好錯過呢個機會，快啲去買返去試下啦。"
            "深山菌子營養豐富又好食，用嚟煲湯定係炒都好正，今日推介俾大家試下品嚐。"
            "真係好好味㗎！"
        )
        # First two calls: first half + second half (Mandarin generation)
        # Third call: to_cantonese conversion
        mock_call_llm.side_effect = [first_json, second_json, cantonese_text]

        gen = self._make_generator()
        result = gen.run(product="羊肚菌", brand="滋元堂", language="cantonese")

        assert isinstance(result, ScriptResult)
        assert "徹底煮熟" in result.full_text
        assert "羊肚菌" in result.full_text
        assert "滋元堂" in result.full_text
        assert result.quality["ok"] is True

    def test_run_cantonese_mock_returns_cantonese_stub(self):
        gen = self._make_generator()
        result = gen.run(
            product="羊肚菌", brand="滋元堂", mock=True, language="cantonese"
        )

        assert isinstance(result, ScriptResult)
        assert result.mock is True
        assert "而家" in result.full_text
        assert "嘅" in result.full_text


class TestValidateScriptWithConfig:
    """validate_script 当 config 参数传入时从配置读取质检规则。"""

    def test_config_overrides_word_count(self):
        """配置中的 word_count_min/max 应替代硬编码 150-200。"""
        # 紧凑字数约 94（优质食材重复 11 次=44，加 羊肚菌 3 + 再重复 11 次=44，加 滋元堂 3）
        text = ("优质食材。" * 11) + "羊肚菌。" + ("优质食材。" * 11) + "滋元堂。"
        config = {"script": {"word_count_min": 50, "word_count_max": 100}}
        result = validate_script(text, "羊肚菌", "滋元堂", config=config)
        assert result["ok"] is True, f"errors: {result['errors']}"

    def test_config_word_count_rejects_outside_range(self):
        """配置的区间生效后，超出区间应报错。"""
        text = "短。" * 3
        config = {"script": {"word_count_min": 100, "word_count_max": 200}}
        result = validate_script(text, "羊肚菌", "滋元堂", config=config)
        assert result["ok"] is False
        assert any("字数不足" in e for e in result["errors"])

    def test_config_custom_forbidden_words(self):
        """配置的 forbidden_words 应替换硬编码禁词列表。"""
        # 填充字数到 150-200，产品/品牌各出现 1 次，"治疗"在文本中
        padding = "今天给大家介绍一款非常好吃的美食。" * 9
        text = padding + "滋元堂今天介绍羊肚菌的做法这种食材来自云南深山可以治疗疾病口感非常好推荐大家尝试购买品尝。"
        config = {"script": {"forbidden_words": ["养生"]}}  # only "养生" is forbidden
        result = validate_script(text, "羊肚菌", "滋元堂", config=config)
        # "治疗" is NOT in the custom forbidden list, so it should pass
        assert result["ok"] is True, f"errors: {result['errors']}"

    def test_config_custom_forbidden_words_catches_its_own(self):
        """自定义禁词列表中的词应被检出。"""
        text = (
            "今天介绍羊肚菌的做法。滋元堂的产品非常养生，充分烹熟后口感非常好。推荐购买。"
            * 3
        )
        config = {"script": {"forbidden_words": ["养生"]}}
        result = validate_script(text, "羊肚菌", "滋元堂", config=config)
        assert result["ok"] is False
        assert any("养生" in e for e in result["errors"])

    def test_config_required_word_count_product(self):
        """配置 required_word_count.product 控制品名出现次数。"""
        padding = "今天给大家介绍一款非常好吃的美食。" * 9  # compact_len=144
        # "羊肚菌" 不出现，但 product=0 表示不要求品名出现
        text = padding + "滋元堂这款产品来自优质产地口感鲜美营养丰富值得推荐。"  # compact_len=25
        config = {"script": {"required_word_count": {"product": 0}}}
        result = validate_script(text, "羊肚菌", "滋元堂", config=config)
        # total compact_len ≈ 169, within 150-200
        assert result["ok"] is True, f"errors: {result['errors']}"

    def test_config_emoji_allowed(self):
        """配置 emoji_forbidden=False 时 emoji 不应被拒。"""
        padding = "今天给大家介绍一款非常好吃的美食。" * 9  # compact_len=144
        text = padding + "羊肚菌是来自云南的美味食材滋元堂精心挑选口感鲜美😊推荐购买。"  # compact_len≈28
        config = {"script": {"emoji_forbidden": False}}
        result = validate_script(text, "羊肚菌", "滋元堂", config=config)
        assert result["ok"] is True, f"errors: {result['errors']}"

    def test_config_emoji_still_checked_when_true(self):
        """配置 emoji_forbidden=True 时 emoji 仍应被拒。"""
        padding = "今天给大家介绍一款非常好吃的美食。" * 9
        text = padding + "羊肚菌是来自云南的美味食材滋元堂精心挑选口感鲜美😊推荐购买。"
        config = {"script": {"emoji_forbidden": True}}
        result = validate_script(text, "羊肚菌", "滋元堂", config=config)
        assert result["ok"] is False
        assert any("emoji" in e.lower() or "表情" in e for e in result["errors"])

    def test_config_max_sentence_length(self):
        """配置 max_sentence_length 应检查每句紧凑字数。"""
        # 单句超长（"非常长的一个句子"*10 紧凑字数=80），产品/品牌各出现一次
        text = "今天介绍羊肚菌的做法。" + "非常长的一个句子" * 10 + "。滋元堂的产品值得信赖。"
        config = {"script": {"max_sentence_length": 30}}
        result = validate_script(text, "羊肚菌", "滋元堂", config=config)
        assert result["ok"] is False
        assert any("超长" in e for e in result["errors"])

    def test_config_no_config_unchanged(self):
        """不传 config 时行为与修改前完全一致。"""
        text = (
            "今天给大家介绍一种美味食材。" * 11
            + "滋元堂的羊肚菌来自云南深山，充分烹熟后口感鲜美，营养丰富。"
        )
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True
        assert result["errors"] == []

    def test_config_empty_dict_no_crash(self):
        """config={} 或 config= {"script": {}} 不应崩溃，应回退到默认。"""
        text = (
            "今天给大家介绍一种美味食材。" * 11
            + "滋元堂的羊肚菌来自云南深山，充分烹熟后口感鲜美，营养丰富。"
        )
        result = validate_script(text, "羊肚菌", "滋元堂", config={})
        assert result["ok"] is True
        result2 = validate_script(text, "羊肚菌", "滋元堂", config={"script": {}})
        assert result2["ok"] is True


class TestValidateCantoneseScriptWithConfig:
    """validate_cantonese_script 当 config 参数传入时从配置读取质检规则。"""

    def test_config_overrides_word_count(self):
        """配置中的 word_count_min/max 应替代硬编码。"""
        text = ("優質食材。" * 11) + "羊肚菌。" + ("優質食材。" * 11) + "滋元堂。"
        config = {"script": {"word_count_min": 50, "word_count_max": 100}}
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂", config=config)
        assert result["ok"] is True, f"errors: {result['errors']}"

    def test_config_custom_forbidden_words(self):
        """自定义禁词列表应替换硬编码列表。"""
        padding = "今日介紹一款非常美味嘅食材。" * 10  # compact_len=130
        text = padding + "羊肚菌係一種美味食材滋元堂品質值得信賴可以治療疾病口感好正。"  # compact_len=29
        config = {"script": {"forbidden_words": ["养生"]}}
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂", config=config)
        # total ≈ 159, within 150-200; "治療" not in custom list
        assert result["ok"] is True, f"errors: {result['errors']}"

    def test_config_emoji_allowed(self):
        """配置 emoji_forbidden=False 时 emoji 不应被拒。"""
        padding = "今日介紹一款非常美味嘅食材。" * 11  # compact_len=143
        text = padding + "羊肚菌係美味食材滋元堂品質值得信賴口感好正😊推薦購買。"  # compact_len≈25
        config = {"script": {"emoji_forbidden": False}}
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂", config=config)
        assert result["ok"] is True, f"errors: {result['errors']}"

    def test_config_no_config_unchanged(self):
        """不传 config 时行为与修改前完全一致。"""
        text = (
            "今日同大家介紹一種美味食材。" * 11
            + "滋元堂嘅羊肚菌嚟自雲南深山，徹底煮熟之後口感好正，營養豐富。"
        )
        result = validate_cantonese_script(text, "羊肚菌", "滋元堂")
        assert result["ok"] is True
        assert result["errors"] == []
