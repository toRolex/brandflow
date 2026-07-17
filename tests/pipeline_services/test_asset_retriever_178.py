"""Tests: retriever produces visual_type for every sentence."""

from __future__ import annotations

from packages.pipeline_services.asset_library.models import AssetRecord, Category
from packages.pipeline_services.asset_library.repository import AssetRepository
from packages.pipeline_services.asset_library.retriever import AssetRetriever


def test_retriever_sets_visual_type_on_matched_clips(tmp_path) -> None:
    db_path = tmp_path / "visual_type.db"
    repo = AssetRepository(db_path)
    repo.insert(
        AssetRecord(
            asset_id="r1",
            file_path="/data/cut.mp4",
            category=Category.CUTTING,
            product="荔枝菌",
            confidence=0.9,
        )
    )
    retriever = AssetRetriever(repo)
    script = "全部匹配的句子。每个都有素材。"
    results = retriever.retrieve(script, "荔枝菌")
    assert len(results) > 0
    for entry in results:
        assert "visual_type" in entry
        assert entry["visual_type"] in ("clip", "unresolved")


def test_retriever_produces_entry_for_every_sentence(tmp_path) -> None:
    """Every sentence gets an entry even when no match is available."""
    db_path = tmp_path / "all_sentences.db"
    repo = AssetRepository(db_path)
    retriever = AssetRetriever(repo)
    script = "句子一内容。句子二描述。句子三总结。"
    results = retriever.retrieve(script, "荔枝菌")
    assert len(results) == 3
    # No assets in DB → all should be unresolved
    for entry in results:
        assert entry["visual_type"] == "unresolved"
        assert entry["file_path"] == ""


def test_retriever_matched_clips_have_clip_visual_type(tmp_path) -> None:
    """Sentences that matched real assets get visual_type=clip."""
    db_path = tmp_path / "matched_clips.db"
    repo = AssetRepository(db_path)
    repo.insert(
        AssetRecord(
            asset_id="r1",
            file_path="/data/cut.mp4",
            category=Category.CUTTING,
            product="荔枝菌",
            confidence=0.9,
            duration_seconds=5.0,
        )
    )
    retriever = AssetRetriever(repo)
    script = "全部匹配只有一个词。"
    results = retriever.retrieve(script, "荔枝菌")
    assert len(results) == 1
    assert results[0]["visual_type"] == "clip"
    assert results[0]["file_path"] == "/data/cut.mp4"
