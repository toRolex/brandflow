from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from packages.knowledge_store.store import KnowledgeStore
from packages.knowledge_store.models import KnowledgeItem
from packages.pipeline_services.script_service.generator import ScriptGenerator, ScriptResult


class TestScriptGeneratorWithKnowledge:
    def _make_generator(self):
        config = MagicMock()
        config.api_key = "test-key"
        config.base_url = "https://api.deepseek.com/v1"
        config.model = "deepseek-v4-pro"
        return ScriptGenerator(config)

    def _populate_store(self, tmp_path: Path) -> KnowledgeStore:
        store = KnowledgeStore(tmp_path)
        items = [
            KnowledgeItem(
                id="sp_001",
                document_id="doc_001",
                type="selling_point",
                title="野生生长环境",
                content="羊肚菌生长在云南海拔2000米以上的原始森林中，纯天然无污染",
                priority=5,
                tags=["产地", "天然"],
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="sp_002",
                document_id="doc_001",
                type="selling_point",
                title="高营养价值",
                content="富含18种氨基酸和多种微量元素，蛋白质含量高达20%",
                priority=4,
                tags=["营养"],
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="sp_003",
                document_id="doc_001",
                type="selling_point",
                title="独特菌菇香气",
                content="烹饪后散发浓郁菌菇香气，口感鲜嫩爽滑",
                priority=3,
                tags=["口感"],
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="sp_004",
                document_id="doc_001",
                type="specification",
                title="包装规格",
                content="每包500g，真空包装",
                priority=2,
                tags=["包装"],
                source_document="产品介绍.txt",
            ),
        ]
        store.save_items(items)
        return store

    @patch.object(ScriptGenerator, "_call_llm")
    def test_run_with_knowledge_config_passes_selling_points_to_prompt(
        self, mock_call_llm, tmp_path: Path
    ):
        """knowledge_config 启用时，卖点应出现在 system prompt 中"""
        store = self._populate_store(tmp_path)

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
        knowledge_config = {
            "enabled": True,
            "store_dir": str(tmp_path),
            "top_k": 3,
        }
        result = gen.run(
            product="羊肚菌",
            brand="滋元堂",
            knowledge_config=knowledge_config,
        )

        assert isinstance(result, ScriptResult)
        assert len(result.full_text) > 0

        # Check that LLM was called and the system prompt contained selling points
        call_args_list = mock_call_llm.call_args_list
        assert len(call_args_list) > 0
        # First call is for first_half
        first_call_messages = call_args_list[0][0][0]
        system_content = first_call_messages[0]["content"]
        # Should contain at least one selling point title
        assert "野生生长环境" in system_content
        assert "高营养价值" in system_content

    @patch.object(ScriptGenerator, "_call_llm")
    def test_run_with_empty_knowledge_does_not_crash(
        self, mock_call_llm, tmp_path: Path
    ):
        """卖点为空时静默跳过，不影响正常生成"""
        store = KnowledgeStore(tmp_path)
        # Store is empty — no items

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
        result = gen.run(
            product="羊肚菌",
            brand="滋元堂",
            knowledge_config={
                "enabled": True,
                "store_dir": str(tmp_path),
                "top_k": 3,
            },
        )
        assert isinstance(result, ScriptResult)
        assert result.full_text != ""

    def test_run_without_knowledge_config_unchanged(self):
        """不传 knowledge_config 时行为不变"""
        gen = self._make_generator()
        result = gen.run(product="羊肚菌", brand="滋元堂", mock=True)
        assert isinstance(result, ScriptResult)
        assert result.mock is True
        assert "羊肚菌" in result.full_text

    def test_run_with_knowledge_config_disabled_unchanged(self):
        """knowledge_config.enabled=False 时不注入卖点"""
        gen = self._make_generator()
        result = gen.run(
            product="羊肚菌",
            brand="滋元堂",
            mock=True,
            knowledge_config={"enabled": False, "store_dir": "/tmp", "top_k": 5},
        )
        assert isinstance(result, ScriptResult)
        assert result.mock is True

    @patch.object(ScriptGenerator, "_call_llm")
    def test_knowledge_in_both_halves(self, mock_call_llm, tmp_path: Path):
        """knowledge 卖点应同时注入前半段和后半段的 system prompt"""
        store = self._populate_store(tmp_path)

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
        gen.run(
            product="羊肚菌",
            brand="滋元堂",
            knowledge_config={
                "enabled": True,
                "store_dir": str(tmp_path),
                "top_k": 3,
            },
        )

        call_args_list = mock_call_llm.call_args_list
        # Check first_half system prompt
        first_messages = call_args_list[0][0][0]
        assert "野生生长环境" in first_messages[0]["content"]
        # Check second_half system prompt
        second_messages = call_args_list[1][0][0]
        assert "野生生长环境" in second_messages[0]["content"]
