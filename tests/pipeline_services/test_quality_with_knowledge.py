from __future__ import annotations

from pathlib import Path

from packages.knowledge_store.models import KnowledgeItem
from packages.knowledge_store.store import KnowledgeStore
from packages.pipeline_services.script_service.quality import validate_script


def _valid_text(*, include_selling: list[str] | None = None) -> str:
    """Create a text with proper word count (150-200), product=1, brand=1.

    The base text includes selling point titles: 野生生长环境, 高营养价值, 独特菌菇香气.
    """
    parts = [
        "野生生长环境孕育了羊肚菌的独特品质。",
        "采自云南高山原始森林每一朵都朵大肉厚品质上乘。",
        "农户手工采摘确保每一朵都完好无损精心挑选。",
        "高营养价值让这道山珍成为滋补佳品富含多种氨基酸和微量元素。",
        "独特菌菇香气在烹饪中弥漫整个厨房口感鲜嫩爽滑让人回味。",
        "烹饪方法简单多样炖汤炒菜都合适家常必备好食材。",
        "滋元堂精选优质食材品质值得您放心选购。",
    ]
    return "".join(parts)


def _valid_text_no_selling() -> str:
    """Create a text with proper word count but no selling point titles."""
    parts = [
        "来自高山的美味食材深受广大食客喜爱和追捧。",
        "每一朵都经过精心挑选品质非常出众优良。",
        "农户手工采摘确保每一朵新鲜和完整。",
        "营养丰富做法多样是家中常备好食材。",
        "口感鲜嫩爽滑让人回味无穷欲罢不能。",
        "炖汤炒菜都非常合适简单方便又美味。",
        "这道来自山野的珍馐佳肴值得每个人细细品尝。",
        "羊肚菌的美味让人难以忘怀久久回味。",
        "滋元堂精选品质值得您放心选购。",
    ]
    return "".join(parts)


class TestQualityKnowledgeRules:
    """Test knowledge_rules in validate_script."""

    def _populate_selling_points(self, store: KnowledgeStore) -> None:
        items = [
            KnowledgeItem(
                id="sp_001",
                document_id="doc_001",
                type="selling_point",
                title="野生生长环境",
                content="生长在云南海拔2000米以上原始森林中",
                priority=5,
                tags=["产地", "天然"],
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="sp_002",
                document_id="doc_001",
                type="selling_point",
                title="高营养价值",
                content="富含18种氨基酸和多种微量元素",
                priority=4,
                tags=["营养"],
                source_document="产品介绍.txt",
            ),
            KnowledgeItem(
                id="sp_003",
                document_id="doc_001",
                type="selling_point",
                title="独特菌菇香气",
                content="烹饪后散发浓郁菌菇香气",
                priority=3,
                tags=["口感"],
                source_document="产品介绍.txt",
            ),
        ]
        store.save_items(items)

    def test_no_knowledge_rules_skipped(self) -> None:
        """不配置 knowledge_rules 时行为不变。"""
        text = "来自优质产地的羊肚菌。滋元堂的品质值得信赖。"
        result = validate_script(text, "羊肚菌", "滋元堂")
        assert "ok" in result
        assert isinstance(result["ok"], bool)

    def test_knowledge_config_none_skipped(self) -> None:
        """config 为 None 时静默跳过。"""
        text = "来自优质产地的羊肚菌。滋元堂的品质值得信赖。"
        result = validate_script(text, "羊肚菌", "滋元堂", config=None)
        assert "ok" in result

    def test_require_top_selling_points_satisfied(self, tmp_path: Path) -> None:
        """脚本包含 top 卖点时通过。"""
        self._populate_selling_points(KnowledgeStore(tmp_path))
        text = _valid_text()
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "require_top_selling_points": True,
                    "store_dir": str(tmp_path),
                    "top_k": 3,
                }
            },
        )
        assert result["ok"] is True, f"Errors: {result['errors']}"

    def test_require_top_selling_points_fails(self, tmp_path: Path) -> None:
        """脚本不包含 top 卖点时失败。"""
        self._populate_selling_points(KnowledgeStore(tmp_path))
        text = _valid_text_no_selling()
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "require_top_selling_points": True,
                    "store_dir": str(tmp_path),
                    "top_k": 3,
                }
            },
        )
        assert result["ok"] is False
        assert any("卖点" in e for e in result["errors"])

    def test_min_selling_points_satisfied(self, tmp_path: Path) -> None:
        """脚本包含足够卖点时通过。"""
        self._populate_selling_points(KnowledgeStore(tmp_path))
        text = _valid_text()
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "min_selling_points_included": 2,
                    "store_dir": str(tmp_path),
                    "top_k": 3,
                }
            },
        )
        assert result["ok"] is True, f"Errors: {result['errors']}"

    def test_min_selling_points_fails(self, tmp_path: Path) -> None:
        """脚本卖点不足时失败。"""
        self._populate_selling_points(KnowledgeStore(tmp_path))
        text = _valid_text_no_selling()
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "min_selling_points_included": 2,
                    "store_dir": str(tmp_path),
                    "top_k": 3,
                }
            },
        )
        assert result["ok"] is False
        assert any("卖点" in e for e in result["errors"])

    def test_min_selling_points_zero_skipped(self, tmp_path: Path) -> None:
        """min_selling_points_included=0 时跳过。"""
        self._populate_selling_points(KnowledgeStore(tmp_path))
        text = "来自优质产地的羊肚菌。滋元堂的品质值得信赖。"
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "min_selling_points_included": 0,
                    "store_dir": str(tmp_path),
                }
            },
        )
        assert isinstance(result["ok"], bool)

    def test_forbidden_words_from_knowledge_satisfied(self, tmp_path: Path) -> None:
        """脚本不含知识库禁词时通过。"""
        store = KnowledgeStore(tmp_path)
        store.save_items([
            KnowledgeItem(
                id="fw_001",
                document_id="doc_001",
                type="forbidden_word",
                title="禁词",
                content="",
                priority=1,
                tags=[],
                source_document="规则.txt",
            ),
        ])
        text = _valid_text()
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "forbidden_words_from_knowledge": True,
                    "store_dir": str(tmp_path),
                }
            },
        )
        assert result["ok"] is True, f"Errors: {result['errors']}"

    def test_forbidden_words_from_knowledge_fails(self, tmp_path: Path) -> None:
        """脚本含知识库禁词时失败。"""
        store = KnowledgeStore(tmp_path)
        store.save_items([
            KnowledgeItem(
                id="fw_001",
                document_id="doc_001",
                type="forbidden_word",
                title="禁词",
                content="劣质",
                priority=1,
                tags=[],
                source_document="规则.txt",
            ),
        ])

        text = _valid_text_no_selling().replace("美味", "劣质")
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "forbidden_words_from_knowledge": True,
                    "store_dir": str(tmp_path),
                }
            },
        )
        assert result["ok"] is False
        assert any("禁词" in e for e in result["errors"])

    def test_require_top_selling_points_empty_store(self, tmp_path: Path) -> None:
        """卖点为空时静默跳过。"""
        text = _valid_text()
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "require_top_selling_points": True,
                    "store_dir": str(tmp_path),
                    "top_k": 3,
                }
            },
        )
        assert result["ok"] is True, f"Errors: {result['errors']}"

    def test_min_selling_points_empty_store(self, tmp_path: Path) -> None:
        """卖点为空时静默跳过 min_selling_points_included。"""
        text = _valid_text()
        result = validate_script(
            text,
            "羊肚菌",
            "滋元堂",
            config={
                "knowledge_rules": {
                    "min_selling_points_included": 2,
                    "store_dir": str(tmp_path),
                    "top_k": 3,
                }
            },
        )
        assert result["ok"] is True, f"Errors: {result['errors']}"
