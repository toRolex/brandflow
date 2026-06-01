import pytest
from packages.pipeline_services.asset_library.models import (
    AssetRecord,
    AssetStatus,
    Category,
    load_keyword_map,
)


class TestCategory:
    def test_all_categories_exist(self):
        assert len(Category) == 10
        assert Category.ORIGIN.value == "产地溯源"
        assert Category.MACRO.value == "产品特写"


class TestAssetRecord:
    def test_create_minimal_record(self):
        record = AssetRecord(
            asset_id="clip_001",
            file_path="/data/荔枝菌/切配处理/clip_001.mp4",
            category=Category.CUTTING,
            product="荔枝菌",
        )
        assert record.status == "available"
        assert record.usage_count == 0
        assert record.confidence == 0.0

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            AssetRecord(
                asset_id="bad",
                file_path="/x.mp4",
                category=Category.MACRO,
                confidence=1.5,
            )


class TestLoadKeywordMap:
    def test_loads_all_categories(self):
        kwmap = load_keyword_map()
        for cat in Category:
            assert cat.value in kwmap, f"Missing category: {cat.value}"

    def test_keywords_are_non_empty(self):
        kwmap = load_keyword_map()
        for cat, keywords in kwmap.items():
            assert len(keywords) > 0, f"Empty keywords for {cat}"
