from __future__ import annotations

from unittest.mock import MagicMock, patch

from packages.pipeline_services.script_service.generator import ScriptGenerator
from packages.pipeline_services.script_service.prompts import (
    build_first_half_messages,
    build_second_half_messages,
)


class TestScriptGeneratorProductConfig:
    """ScriptGenerator 应从 ProductConfig 读取 scene/material"""

    def _make_generator(self) -> ScriptGenerator:
        cfg = MagicMock()
        cfg.api_key = "test-key"
        cfg.base_url = "https://test.url"
        cfg.model = "test-model"
        return ScriptGenerator(cfg)

    @patch("packages.pipeline_services.script_service.generator.LLMClient")
    def test_run_with_product_config_uses_config_scene(self, mock_llm):
        """传入 product_config 时使用配置的 scene"""
        mock_instance = MagicMock()
        mock_instance.post.return_value = {
            "sentence_1": "第一句。",
            "sentence_2": "第二句。",
            "sentence_3": "第三句。",
            "sentence_4": "第四句。",
        }
        mock_llm.return_value = mock_instance

        gen = self._make_generator()
        result = gen.run(
            product="测试产品",
            brand="测试品牌",
            product_config={
                "script": {
                    "scene": "开箱场景、产品特写",
                    "material": "包装打开、产品展示",
                }
            },
            mock=True,
        )
        assert result.mock is True

    @patch("packages.pipeline_services.script_service.generator.LLMClient")
    def test_run_without_product_config_uses_defaults(self, mock_llm):
        """不传 product_config 时使用 prompts.py 的 DEFAULT_* 常量"""
        mock_instance = MagicMock()
        mock_instance.post.return_value = {
            "sentence_1": "第一句。",
            "sentence_2": "第二句。",
            "sentence_3": "第三句。",
            "sentence_4": "第四句。",
        }
        mock_llm.return_value = mock_instance

        gen = self._make_generator()
        result = gen.run(
            product="测试产品",
            brand="测试品牌",
            mock=True,
        )
        assert result.mock is True


class TestBuildMessagesProductConfig:
    """build_first_half_messages / build_second_half_messages 应从 product_config 读取"""

    def test_first_half_uses_product_config_scene(self):
        """product_config 传入时 scene 应替换默认值"""
        msgs = build_first_half_messages(
            product="零食",
            brand="某品牌",
            product_config={
                "script": {
                    "scene": "自定义开箱场景",
                    "material": "自定义素材描述",
                }
            },
        )
        user_content = msgs[1]["content"]
        assert "自定义开箱场景" in user_content
        assert "自定义素材描述" in user_content
        # 旧默认值中的食品术语不应出现
        assert "食材展示" not in user_content
        assert "食材近景" not in user_content

    def test_first_half_without_product_config_uses_defaults(self):
        """不传 product_config 时使用 DEFAULT_SCENE（默认值为空，不生成场景/素材行）"""
        msgs = build_first_half_messages(
            product="零食",
            brand="某品牌",
        )
        user_content = msgs[1]["content"]
        # 默认值为空字符串时，user prompt 不包含场景和素材画面行
        assert "场景：" not in user_content
        assert "素材画面：" not in user_content

    def test_first_half_uses_product_config_system_prompt(self):
        """product_config 传入时 system_prompt 应替换默认值"""
        msgs = build_first_half_messages(
            product="零食",
            brand="某品牌",
            product_config={
                "script": {
                    "system_prompt": "你是一位零食文案专家。",
                }
            },
        )
        system_content = msgs[0]["content"]
        assert "零食文案专家" in system_content
        assert "食品产品" not in system_content

    def test_second_half_uses_product_config_system_prompt(self):
        """build_second_half_messages system_prompt 也来自 product_config"""
        msgs = build_second_half_messages(
            product="零食",
            brand="某品牌",
            first_half="前半段文案。",
            first_length=5,
            product_config={
                "script": {
                    "system_prompt": "你是一位零食文案专家。",
                }
            },
        )
        system_content = msgs[0]["content"]
        assert "零食文案专家" in system_content
        assert "食品产品" not in system_content
