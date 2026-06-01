import pytest
from pathlib import Path
from packages.pipeline_services.asset_library.models import AssetRecord, Category
from packages.pipeline_services.asset_library.repository import AssetRepository


@pytest.fixture
def repo(tmp_path):
    db = tmp_path / "test_assets.db"
    r = AssetRepository(db)
    yield r
    if db.exists():
        db.unlink()


def test_insert_and_query(repo):
    record = AssetRecord(
        asset_id="test_001",
        file_path="/data/test.mp4",
        category=Category.CUTTING,
        product="荔枝菌",
        confidence=0.9,
    )
    repo.insert(record)

    results = repo.query_by_category("荔枝菌", Category.CUTTING)
    assert len(results) == 1
    assert results[0].asset_id == "test_001"


def test_query_returns_empty_for_wrong_product(repo):
    record = AssetRecord(
        asset_id="test_002",
        file_path="/data/test.mp4",
        category=Category.CUTTING,
        product="荔枝菌",
    )
    repo.insert(record)
    results = repo.query_by_category("羊肚菌", Category.CUTTING)
    assert len(results) == 0


def test_increment_usage(repo):
    record = AssetRecord(asset_id="test_003", file_path="/d.mp4", category=Category.MACRO, product="荔枝菌")
    repo.insert(record)
    repo.increment_usage("test_003")
    assert repo.get_usage_count("test_003") == 1


def test_disabled_assets_not_returned(repo):
    record = AssetRecord(asset_id="test_004", file_path="/d.mp4", category=Category.MACRO, product="荔枝菌")
    repo.insert(record)
    repo.update_status("test_004", "disabled")
    results = repo.query_by_category("荔枝菌", Category.MACRO)
    assert len(results) == 0


def test_usage_sort_order(repo):
    for i in range(3):
        repo.insert(AssetRecord(asset_id=f"a{i}", file_path=f"/d{i}.mp4", category=Category.MACRO, product="荔枝菌"))
    repo.increment_usage("a1")
    repo.increment_usage("a1")
    repo.increment_usage("a0")
    results = repo.query_by_category("荔枝菌", Category.MACRO)
    assert results[0].asset_id == "a2"
    assert results[-1].asset_id == "a1"
