import pytest
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
            product="荔枝菌",
            confidence=0.8,
        ))
    yield r


def test_retrieve_matches_with_classify(repo):
    def classify_fn(sentence: str) -> str | None:
        if "切" in sentence:
            return "切配处理"
        if "翻炒" in sentence or "烹熟" in sentence:
            return "烹饪翻炒"
        return None

    retriever = AssetRetriever(repo, classify_fn=classify_fn)
    script = "荔枝菌切好以后下锅翻炒。充分烹熟后出锅装盘。"
    results = retriever.retrieve(script, "荔枝菌")
    assert len(results) >= 1
    categories = [r["category"] for r in results]
    assert "切配处理" in categories or "烹饪翻炒" in categories


def test_retrieve_fallback_when_no_match(repo):
    retriever = AssetRetriever(repo)
    script = "今天天气真好。出去散步。"
    results = retriever.retrieve(script, "荔枝菌")
    assert len(results) == 2
    assert all(r["method"] == "fallback" for r in results)


def test_retrieve_includes_duration_seconds(tmp_path):
    db_path = tmp_path / "duration_test.db"
    repo = AssetRepository(db_path)
    repo.insert(AssetRecord(
        asset_id="dur-1",
        file_path="/data/clip.mp4",
        category=Category.CUTTING,
        product="荔枝菌",
        confidence=0.9,
        duration_seconds=7.5,
    ))

    def classify_fn(sentence: str) -> str | None:
        return Category.CUTTING.value if sentence else None

    retriever = AssetRetriever(repo, classify_fn=classify_fn)
    results = retriever.retrieve("把荔枝菌切好。", "荔枝菌")

    assert results[0]["duration_seconds"] == 7.5


def test_split_sentences():
    text = "第一句话。第二句话！第三句话？第四句话\n第五句话"
    result = AssetRetriever._split_sentences(text)
    assert len(result) == 5
