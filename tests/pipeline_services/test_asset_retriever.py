import pytest
from pathlib import Path
from packages.pipeline_services.asset_library.models import AssetRecord, Category
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.asset_library.retriever import AssetRetriever


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "retriever_test.db"
    r = AssetRepository(db_path)
    for i, cat in enumerate([Category.CUTTING, Category.STIR_FRY, Category.MACRO]):
        r.insert(AssetRecord(
            asset_id=f"r{i}",
            file_path=f"/data/{cat.value}/clip_{i}.mp4",
            category=cat,
            product="见手青",
            confidence=0.8,
        ))
    yield r


def test_retrieve_matches_keywords(repo):
    retriever = AssetRetriever(repo)
    script = "见手青切好以后下锅翻炒。充分烹熟后出锅装盘。"
    results = retriever.retrieve(script, "见手青")
    assert len(results) >= 1
    categories = [r["category"] for r in results]
    assert "切配处理" in categories or "烹饪翻炒" in categories


def test_retrieve_fallback_when_no_match(repo):
    retriever = AssetRetriever(repo)
    script = "今天天气真好。出去散步。"
    results = retriever.retrieve(script, "见手青")
    assert len(results) == 2
    assert all(r["method"] == "fallback" for r in results)


def test_split_sentences():
    text = "第一句话。第二句话！第三句话？第四句话\n第五句话"
    result = AssetRetriever._split_sentences(text)
    assert len(result) == 5
