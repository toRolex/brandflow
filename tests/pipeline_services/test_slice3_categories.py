"""Tests for Phase 2 Slice 3 — Configurable Asset Categories."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


from packages.pipeline_services.asset_library import (
    Category,
    CategoryConfig,
)
from packages.pipeline_services.asset_library.category_config import (
    default_categories,
    get_categories,
)
from packages.pipeline_services.asset_library.classify import (
    build_classify_prompt,
    create_classify_fn,
)
from packages.pipeline_services.asset_library.vision_client import (
    build_vision_prompt,
    VisionClient,
)

# ---------------------------------------------------------------------------
# CategoryConfig dataclass
# ---------------------------------------------------------------------------


class TestCategoryConfig:
    def test_create_minimal(self) -> None:
        cfg = CategoryConfig(id="origin", name="产地溯源")
        assert cfg.id == "origin"
        assert cfg.name == "产地溯源"
        assert cfg.description == ""
        assert cfg.vision_prompt == ""

    def test_create_full(self) -> None:
        cfg = CategoryConfig(
            id="stir_fry",
            name="烹饪翻炒",
            description="翻炒锅气特写",
            vision_prompt="识别铁锅翻炒动作",
        )
        assert cfg.id == "stir_fry"
        assert cfg.name == "烹饪翻炒"
        assert cfg.description == "翻炒锅气特写"
        assert cfg.vision_prompt == "识别铁锅翻炒动作"

    def test_default_categories_match_enum(self) -> None:
        defaults = default_categories()
        assert len(defaults) == 10
        enum_names = [c.value for c in Category]
        default_names = [c.name for c in defaults]
        for name in enum_names:
            assert name in default_names, f"Missing default: {name}"


# ---------------------------------------------------------------------------
# get_categories() with ConfigReader / ProductStore
# ---------------------------------------------------------------------------


def _make_reader(tmpdir: str):
    """Helper: create a ConfigReader pointing at *tmpdir*."""
    from packages.provider_config.config_reader import ConfigReader

    return ConfigReader(config_dir=tmpdir)


def _make_store(tmpdir: str):
    """Helper: create a ProductStore with real ConfigReader and config_path."""
    from packages.provider_config.config_reader import ConfigReader
    from packages.provider_config.config_reader import ProductStore

    config_path = Path(tmpdir) / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    reader = ConfigReader(config_dir=tmpdir)
    return ProductStore(reader=reader, config_path=config_path)


class TestAppConfigCategories:
    def test_get_categories_default(self) -> None:
        """Empty config should return the default food categories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            reader = _make_reader(tmpdir)
            cats = get_categories(reader)
            assert len(cats) == 10
            assert cats[0].name == "产地溯源"
            assert cats[-1].name == "产品特写"

    def test_get_categories_from_config(self) -> None:
        """Config file categories should override defaults."""
        custom_cats = [
            {"id": "harvest", "name": "采收采集"},
            {"id": "processing", "name": "加工处理"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps(
                    {"asset_library": {"categories": custom_cats}}, ensure_ascii=False
                ),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            cats = get_categories(reader)
            assert len(cats) == 2
            assert cats[0].id == "harvest"
            assert cats[0].name == "采收采集"
            assert cats[1].id == "processing"
            assert cats[1].name == "加工处理"

    def test_get_categories_empty_list_in_config(self) -> None:
        """Explicit empty list in config should return defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps({"asset_library": {"categories": []}}, ensure_ascii=False),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            cats = get_categories(reader)
            assert len(cats) == 10  # fallback to defaults
            assert cats[0].name == "产地溯源"

    def test_get_categories_from_product_config(self) -> None:
        """Product-level categories should take priority over asset_library."""
        product_cats = [
            {"id": "promo", "name": "促销活动"},
            {"id": "unboxing", "name": "开箱展示"},
        ]
        al_cats = [
            {"id": "origin", "name": "产地溯源"},
        ]
        config = {
            "product": {"categories": product_cats},
            "asset_library": {"categories": al_cats},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps(config, ensure_ascii=False),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            cats = get_categories(reader, product_id=reader.active_product_id or None)
            assert len(cats) == 2
            assert cats[0].id == "promo"
            assert cats[0].name == "促销活动"
            assert cats[1].id == "unboxing"
            assert cats[1].name == "开箱展示"

    def test_get_categories_empty_product_falls_to_asset_library(self) -> None:
        """Empty product.categories should fall back to asset_library.categories."""
        al_cats = [
            {"id": "origin", "name": "产地溯源"},
            {"id": "stir_fry", "name": "烹饪翻炒"},
        ]
        config = {
            "product": {"categories": []},
            "asset_library": {"categories": al_cats},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps(config, ensure_ascii=False),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            cats = get_categories(reader)
            assert len(cats) == 2
            assert cats[0].id == "origin"
            assert cats[0].name == "产地溯源"
            assert cats[1].id == "stir_fry"
            assert cats[1].name == "烹饪翻炒"

    def test_get_categories_both_empty_returns_defaults(self) -> None:
        """Both product.categories and asset_library.categories empty returns defaults."""
        config = {
            "product": {"categories": []},
            "asset_library": {"categories": []},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps(config, ensure_ascii=False),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            cats = get_categories(reader)
            assert len(cats) == 10  # fallback to defaults
            assert cats[0].name == "产地溯源"

    # ── S1: products[] list format with active_product_id ──

    def test_get_categories_from_products_list_format(self) -> None:
        """Product-level categories via new products[] list + active_product_id format."""
        product_cats = [
            {"id": "harvest", "name": "采收采集", "description": "野外采收"},
            {"id": "drying", "name": "晾晒干燥", "description": "自然晾晒"},
        ]
        config = {
            "products": [
                {
                    "id": "snack_001",
                    "default_name": "零食产品",
                    "categories": product_cats,
                },
            ],
            "active_product_id": "snack_001",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps(config, ensure_ascii=False),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            cats = get_categories(reader, product_id=reader.active_product_id or None)
            assert len(cats) == 2
            assert cats[0].id == "harvest"
            assert cats[0].name == "采收采集"
            assert cats[0].description == "野外采收"
            assert cats[1].id == "drying"
            assert cats[1].name == "晾晒干燥"
            assert cats[1].description == "自然晾晒"

    def test_get_categories_products_list_no_categories_falls_back(self) -> None:
        """Product has no categories field -> fall back to asset_library or defaults."""
        config = {
            "products": [
                {
                    "id": "snack_002",
                    "default_name": "无分类产品",
                },
            ],
            "active_product_id": "snack_002",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps(config, ensure_ascii=False),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            cats = get_categories(reader, product_id=reader.active_product_id or None)
            # Should fall back to default food categories (10)
            assert len(cats) == 10
            assert cats[0].name == "产地溯源"

    def test_get_categories_products_list_empty_categories_falls_back(self) -> None:
        """Product has empty categories list -> fall back to asset_library or defaults."""
        config = {
            "products": [
                {
                    "id": "snack_003",
                    "default_name": "空分类产品",
                    "categories": [],
                },
            ],
            "active_product_id": "snack_003",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps(config, ensure_ascii=False),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            cats = get_categories(reader, product_id=reader.active_product_id or None)
            assert len(cats) == 10  # fallback to defaults
            assert cats[0].name == "产地溯源"

    # ── S2: save_product_config() persists categories ──

    def test_save_product_config_persists_categories(self) -> None:
        """save_product_config() should persist categories and they are readable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_cat")
            store.save_product_config(
                "prod_cat",
                {
                    "categories": [
                        {
                            "id": "origin",
                            "name": "产地溯源",
                            "description": "原产地场景",
                        },
                        {"id": "sorting", "name": "筛选分拣", "description": ""},
                    ],
                },
            )
            cats = get_categories(store._reader, product_id="prod_cat")
            assert len(cats) == 2
            assert cats[0].id == "origin"
            assert cats[0].name == "产地溯源"
            assert cats[0].description == "原产地场景"
            assert cats[1].id == "sorting"
            assert cats[1].name == "筛选分拣"
            assert cats[1].description == ""

    def test_save_product_config_categories_roundtrip(self) -> None:
        """Categories saved via save_product_config() survive reload from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store1 = _make_store(tmpdir)
            store1.switch_product("prod_roundtrip")
            store1.save_product_config(
                "prod_roundtrip",
                {
                    "categories": [
                        {
                            "id": "test_cat",
                            "name": "测试分类",
                            "description": "往返测试",
                        },
                    ],
                },
            )
            # Reload from disk with fresh reader
            reader2 = _make_reader(tmpdir)
            cats = get_categories(reader2, product_id="prod_roundtrip")
            assert len(cats) == 1
            assert cats[0].id == "test_cat"
            assert cats[0].name == "测试分类"
            assert cats[0].description == "往返测试"

    def test_get_category_suggestion_model_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reader = _make_reader(tmpdir)
            assert reader.get_category_suggestion_model() == "deepseek-v4-flash"

    def test_get_category_suggestion_model_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            config_path.write_text(
                json.dumps(
                    {"asset_library": {"category_suggestion_model": "custom-model"}},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            reader = _make_reader(tmpdir)
            assert reader.get_category_suggestion_model() == "custom-model"

    def test_get_category_suggestion_sample_size_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reader = _make_reader(tmpdir)
            assert reader.get_category_suggestion_sample_size() == 20

    def test_get_asset_library_config_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            reader = _make_reader(tmpdir)
            cfg = reader.get_asset_library_config()
            assert "categories" in cfg
            assert "category_suggestion_model" in cfg
            assert cfg["category_suggestion_model"] == "deepseek-v4-flash"
            assert cfg["category_suggestion_sample_size"] == 20


# ---------------------------------------------------------------------------
# classify.py — configurable prompt and function
# ---------------------------------------------------------------------------


class TestClassifyPrompt:
    def test_build_prompt_default(self) -> None:
        """Default prompt (no categories) should use adaptive mode."""
        prompt = build_classify_prompt()
        assert "给出一个简洁的中文分类名称" in prompt
        assert "产地溯源" not in prompt

    def test_build_prompt_custom(self) -> None:
        prompt = build_classify_prompt(["采收采集", "加工处理"])
        assert "采收采集" in prompt
        assert "加工处理" in prompt
        assert "产地溯源" not in prompt

    def test_build_prompt_empty_fallback(self) -> None:
        """Empty list should use adaptive prompt (no food fallback)."""
        prompt = build_classify_prompt([])
        assert "给出一个简洁的中文分类名称" in prompt
        assert "产地溯源" not in prompt

    def test_build_prompt_none_fallback(self) -> None:
        """None should use adaptive prompt (no food fallback)."""
        prompt = build_classify_prompt(None)
        assert "给出一个简洁的中文分类名称" in prompt
        assert "产地溯源" not in prompt


class TestCreateClassifyFnWithCategories:
    """Test that create_classify_fn accepts category_names parameter."""

    def test_custom_categories_classify(self) -> None:
        """Classification with custom categories should validate against them."""
        from unittest.mock import Mock

        mock_resp = Mock()
        mock_resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": '{"category": "采收采集"}'}}]}
        ).encode("utf-8")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
                category_names=["采收采集", "加工处理"],
            )
            result = fn("正在采摘新鲜的荔枝菌。")

        assert result == "采收采集"

    def test_custom_categories_rejects_unknown(self) -> None:
        """Classification should return None for categories not in the allowed list."""
        from unittest.mock import Mock

        mock_resp = Mock()
        mock_resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": '{"category": "产地溯源"}'}}]}
        ).encode("utf-8")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
                category_names=["采收采集", "加工处理"],
            )
            result = fn("随便一句话。")

        assert result is None  # 产地溯源 not in allowed list


class TestClassifyFnBackwardCompat:
    """Test that create_classify_fn works in adaptive mode without category_names."""

    def test_adaptive_classify_accepts_any_category(self) -> None:
        """Without category_names, adaptive mode accepts any category from LLM."""
        from unittest.mock import Mock

        mock_resp = Mock()
        mock_resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": '{"category": "烹饪翻炒"}'}}]}
        ).encode("utf-8")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
            )
            result = fn("翻炒均匀后出锅装盘。")

        assert result == "烹饪翻炒"

    def test_prompt_includes_categories(self) -> None:
        """The LLM prompt should include the category names."""
        with patch("urllib.request.urlopen") as mock_urlopen:
            from unittest.mock import Mock

            mock_resp = Mock()
            mock_resp.read.return_value = json.dumps(
                {"choices": [{"message": {"content": '{"category": "产地溯源"}'}}]}
            ).encode("utf-8")
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
                category_names=["采收采集"],
            )
            fn("测试。")

            call_args = mock_urlopen.call_args[0][0]
            req_body = json.loads(call_args.data)
            messages = req_body["messages"]
            system_content = messages[0]["content"]
            assert "采收采集" in system_content


# ---------------------------------------------------------------------------
# vision_client.py — configurable prompt
# ---------------------------------------------------------------------------


class TestVisionPrompt:
    def test_build_vision_prompt_default(self) -> None:
        prompt = build_vision_prompt()
        assert "可选类别" in prompt
        assert "产地溯源" in prompt
        assert "产品特写" in prompt

    def test_build_vision_prompt_custom(self) -> None:
        prompt = build_vision_prompt(["采收采集", "加工处理"])
        assert "采收采集" in prompt
        assert "加工处理" in prompt
        assert "产地溯源" not in prompt

    def test_build_vision_prompt_empty_fallback(self) -> None:
        prompt = build_vision_prompt([])
        assert "产地溯源" in prompt  # fallback

    def test_build_vision_prompt_none_fallback(self) -> None:
        prompt = build_vision_prompt(None)
        assert "产地溯源" in prompt  # fallback


class TestVisionClientWithCategories:
    def test_vision_client_accepts_categories(self) -> None:
        client = VisionClient(
            api_key="test",
            endpoint="https://api.example.com",
            model="test-model",
            categories=["采收采集", "加工处理"],
        )
        assert "采收采集" in client._vision_prompt
        assert "加工处理" in client._vision_prompt
        assert "产地溯源" not in client._vision_prompt


class TestVisionClientBackwardCompat:
    def test_vision_client_without_categories(self) -> None:
        """Without categories, should use old food categories."""
        client = VisionClient()
        assert "可选类别" in client._vision_prompt
        assert "产地溯源" in client._vision_prompt
        assert "产品特写" in client._vision_prompt


# ---------------------------------------------------------------------------
# Backward compatibility — old Category enum still works
# ---------------------------------------------------------------------------


class TestOldCategoryBackwardCompat:
    def test_enum_still_exists(self) -> None:
        assert Category.ORIGIN.value == "产地溯源"
        assert Category.MACRO.value == "产品特写"

    def test_enum_has_ten_members(self) -> None:
        assert len(Category) == 10

    def test_enum_still_usable_in_asset_record(self) -> None:
        from packages.pipeline_services.asset_library import AssetRecord

        record = AssetRecord(
            asset_id="test_001",
            file_path="/data/test.mp4",
            category=Category.CUTTING,
            product="荔枝菌",
        )
        assert record.category_name() == "切配处理"
        assert record.category == "切配处理"
        assert isinstance(record.category, str)

    def test_category_name_method(self) -> None:
        from packages.pipeline_services.asset_library import AssetRecord

        record = AssetRecord(
            asset_id="test_002",
            file_path="/data/test.mp4",
            category=Category.MACRO,
            product="羊肚菌",
        )
        assert record.category_name() == "产品特写"


# ---------------------------------------------------------------------------
# Import from asset_library package
# ---------------------------------------------------------------------------


class TestPackageExports:
    def test_category_config_imported(self) -> None:
        from packages.pipeline_services.asset_library import CategoryConfig

        assert CategoryConfig is not None

    def test_category_imported(self) -> None:
        from packages.pipeline_services.asset_library import Category

        assert Category is not None

    def test_old_import_still_works(self) -> None:
        """Old imports like ``from ...models import Category`` still work."""
        from packages.pipeline_services.asset_library.models import (
            Category as OldCategory,
        )

        assert OldCategory is Category

    def test_new_import_works(self) -> None:
        """New imports like ``from ...category_config import CategoryConfig`` work."""
        from packages.pipeline_services.asset_library.category_config import (
            CategoryConfig,
        )

        assert CategoryConfig is not None


# ---------------------------------------------------------------------------
# Empty categories edge cases
# ---------------------------------------------------------------------------


class TestEmptyCategories:
    def test_empty_categories_uses_adaptive_mode(self) -> None:
        """Empty categories list should use adaptive mode — accept any category name."""
        from unittest.mock import Mock

        mock_resp = Mock()
        mock_resp.read.return_value = json.dumps(
            {"choices": [{"message": {"content": '{"category": "no_match"}'}}]}
        ).encode("utf-8")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__.return_value = mock_resp
            fn = create_classify_fn(
                api_url="https://api.deepseek.com/chat/completions",
                api_key="sk-test",
                model="deepseek-v4-pro",
                category_names=[],
            )
            # Adaptive mode accepts any non-empty category name
            result = fn("测试。")
        assert result == "no_match"

    def test_empty_categories_does_not_crash_vision(self) -> None:
        """Empty categories list should not crash VisionClient."""
        client = VisionClient(
            api_key="test",
            endpoint="https://api.example.com",
            model="test-model",
            categories=[],
        )
        assert "产地溯源" in client._vision_prompt  # fallback
