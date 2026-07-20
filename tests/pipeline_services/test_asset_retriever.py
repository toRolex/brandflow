import pytest
from packages.pipeline_services.asset_library.models import AssetRecord, Category
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.asset_library.retriever import AssetRetriever


@pytest.fixture
def repo(tmp_path):
    db_path = tmp_path / "retriever_test.db"
    r = AssetRepository(db_path)
    for i, cat in enumerate([Category.CUTTING, Category.STIR_FRY, Category.MACRO]):
        r.insert(
            AssetRecord(
                asset_id=f"r{i}",
                file_path=f"/data/{cat.value}/clip_{i}.mp4",
                category=cat,
                product="荔枝菌",
                confidence=0.8,
            )
        )
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
    repo.insert(
        AssetRecord(
            asset_id="dur-1",
            file_path="/data/clip.mp4",
            category=Category.CUTTING,
            product="荔枝菌",
            confidence=0.9,
            duration_seconds=7.5,
        )
    )

    def classify_fn(sentence: str) -> str | None:
        return Category.CUTTING.value if sentence else None

    retriever = AssetRetriever(repo, classify_fn=classify_fn)
    results = retriever.retrieve("把荔枝菌切好。", "荔枝菌")

    assert results[0]["duration_seconds"] == 7.5


class TestScriptSentenceUnification:
    """Retriever delegates to canonical parse_script_sentences().

    Verifies all acceptance criteria for unified sentence splitting:
    - semicolons are clause punctuation, not sentence boundaries
    - short sentences (< 4 chars) are preserved
    - Chinese/English mixed punctuation handled consistently
    - consecutive punctuation is one sentence
    - newlines end sentences
    - retriever output carries stable sentence_index
    """

    @pytest.mark.parametrize(
        "text,expected",
        [
            # Basic sentence-ending punctuation
            ("第一句话。第二句话！第三句话？", ["第一句话。", "第二句话！", "第三句话？"]),
            # Line breaks
            ("第一行\n第二行", ["第一行", "第二行"]),
            # Mixed: line break after punctuation does not duplicate
            ("第一句。\n第二句。", ["第一句。", "第二句。"]),
            # Semicolons (both Chinese and English) are clause punctuation, NOT boundaries
            ("切菜；这是第一步。翻炒；这是第二步！", ["切菜；这是第一步。", "翻炒；这是第二步！"]),
            # English semicolons and periods: . is not in sentence-end regex;
            # only ! ? are sentence-ending in English in the canonical parser
            ("切菜; 这是第一步. 翻炒; 这是第二步!", ["切菜; 这是第一步. 翻炒; 这是第二步!"]),
            # Short sentences preserved (no minimum length filter)
            ("好。坏。去吧。", ["好。", "坏。", "去吧。"]),
            ("去。来。走。", ["去。", "来。", "走。"]),
            # Chinese + English mixed punctuation
            ("Hello! 你好。How are you?", ["Hello!", "你好。", "How are you?"]),
            # Consecutive punctuation stays as one sentence
            ("你好！！！今天真好。", ["你好！！！", "今天真好。"]),
            # Empty / whitespace only
            ("", []),
            ("   \n\t  ", []),
            # Clause punctuation (comma, semicolon, colon) does NOT split
            ("你好，世界；今天天气：晴朗。", ["你好，世界；今天天气：晴朗。"]),
            # Mixed clause and sentence punctuation
            (
                "今天，天气很好；我们出去玩！回来再吃饭。",
                ["今天，天气很好；我们出去玩！", "回来再吃饭。"],
            ),
            # Multiple empty lines ignored
            ("第一句。\n\n\n第二句。", ["第一句。", "第二句。"]),
        ],
    )
    def test_unified_sentence_splitting(self, text, expected):
        """All boundary cases use the same canonical parser via retriever."""
        from packages.pipeline_services.script_sentence import parse_script_sentences

        result = parse_script_sentences(text)
        assert result == expected

    def test_retriever_output_includes_sentence_index(self, tmp_path):
        """Each clip dict carries sentence_index matching canonical position."""
        from packages.pipeline_services.asset_library.repository import (
            AssetRepository,
        )

        db_path = tmp_path / "index_test.db"
        repo = AssetRepository(db_path)
        repo.insert(
            AssetRecord(
                asset_id="idx-1",
                file_path="/data/clip.mp4",
                category=Category.CUTTING,
                product="荔枝菌",
                confidence=0.9,
                duration_seconds=5.0,
            )
        )

        def classify_fn(sentence: str) -> str | None:
            return Category.CUTTING.value if sentence else None

        retriever = AssetRetriever(repo, classify_fn=classify_fn)

        # Script with 3 sentences of varying lengths (including a short 2-char one)
        script = "把荔枝菌切好。炒。大火烹熟后出锅装盘。"
        results = retriever.retrieve(script, "荔枝菌")

        assert len(results) == 3, f"Expected 3 sentences, got {len(results)}"
        for i, r in enumerate(results):
            assert r["sentence_index"] == i, (
                f"Result {i} sentence_index={r.get('sentence_index')}, expected {i}"
            )

    def test_short_sentence_not_discarded_by_retriever(self, tmp_path):
        """短句（< 4 字符）不再被资源检索阶段丢弃."""
        from packages.pipeline_services.asset_library.repository import (
            AssetRepository,
        )

        db_path = tmp_path / "short_test.db"
        repo = AssetRepository(db_path)
        repo.insert(
            AssetRecord(
                asset_id="s-1",
                file_path="/data/clip.mp4",
                category=Category.MACRO,
                product="荔枝菌",
                confidence=0.9,
                duration_seconds=5.0,
            )
        )

        def classify_fn(sentence: str) -> str | None:
            return Category.MACRO.value if sentence else None

        retriever = AssetRetriever(repo, classify_fn=classify_fn)

        # Short sentences that the old _split_sentences would discard (len < 4)
        script = "好。坏。去吧。"
        results = retriever.retrieve(script, "荔枝菌")

        assert len(results) == 3, (
            f"Expected 3 short sentences, got {len(results)}: results={results}"
        )
