"""Tests for LLM-based asset classification and retrieval."""

import pytest
from packages.pipeline_services.asset_library.models import AssetRecord, Category
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.asset_library.retriever import AssetRetriever


@pytest.fixture
def classify_fn():
    """返回固定的分类函数，模拟 LLM 行为。"""

    def _classify(sentence: str) -> str | None:
        mapping = {
            "切": "切配处理",
            "炒": "烹饪翻炒",
            "山": "产地溯源",
            "鲜": "试吃品尝",
        }
        for key, cat in mapping.items():
            if key in sentence:
                return cat
        return None

    return _classify


@pytest.fixture
def repo_with_assets(tmp_path):
    """创建包含多分类多个素材的仓库。"""
    db_path = tmp_path / "llm_retrieve_test.db"
    r = AssetRepository(db_path)
    assets = [
        ("c1", Category.CUTTING, "/data/cut/a.mp4"),
        ("c2", Category.CUTTING, "/data/cut/b.mp4"),
        ("s1", Category.STIR_FRY, "/data/stir/a.mp4"),
        ("s2", Category.STIR_FRY, "/data/stir/b.mp4"),
        ("o1", Category.ORIGIN, "/data/origin/a.mp4"),
        ("t1", Category.TASTING, "/data/taste/a.mp4"),
        ("m1", Category.MACRO, "/data/macro/a.mp4"),
    ]
    for aid, cat, path in assets:
        r.insert(AssetRecord(
            asset_id=aid,
            file_path=path,
            category=cat,
            product="荔枝菌",
            confidence=0.85,
        ))
    return r


class TestLLMClassification:
    """检索器使用 LLM 分类函数而非关键词映射。"""

    def test_uses_classify_fn_not_keyword_map(self, repo_with_assets, classify_fn):
        """检索时应调用 classify_fn 确定分类，而非查 keyword_map。"""
        retriever = AssetRetriever(repo_with_assets, classify_fn=classify_fn)
        script = "切好备用。翻炒均匀。"

        results = retriever.retrieve(script, "荔枝菌")

        assert len(results) == 2
        categories = {r["category"] for r in results}
        assert "切配处理" in categories
        assert "烹饪翻炒" in categories

    def test_method_is_llm_match(self, repo_with_assets, classify_fn):
        """LLM 分类成功的素材 method 应为 llm_match。"""
        retriever = AssetRetriever(repo_with_assets, classify_fn=classify_fn)
        script = "切片处理。"

        results = retriever.retrieve(script, "荔枝菌")

        assert len(results) == 1
        assert results[0]["method"] == "llm_match"
        assert results[0]["category"] == "切配处理"

    def test_random_selection_within_category(self, repo_with_assets, classify_fn):
        """同一分类内有多个素材时，应随机选取而非固定选 usage_count 最小的。"""
        retriever = AssetRetriever(repo_with_assets, classify_fn=classify_fn)
        script = "开始切片。继续切块。"

        results = retriever.retrieve(script, "荔枝菌")

        assert len(results) == 2
        assert all(r["category"] == "切配处理" for r in results)
        assert all(r["method"] == "llm_match" for r in results)

    def test_retriever_works_without_keyword_map(self, repo_with_assets, classify_fn):
        """检索器不应再依赖 keyword_map.json。"""
        retriever = AssetRetriever(repo_with_assets, classify_fn=classify_fn)
        assert not hasattr(retriever, "keyword_map")
