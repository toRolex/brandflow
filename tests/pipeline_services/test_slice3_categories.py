"""Tests for Phase 2 Slice 3 — Configurable Asset Categories."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from packages.pipeline_services.asset_library import (
    Category,
    CategoryConfig,
)
from packages.pipeline_services.asset_library.category_config import (
    default_categories,
)
from packages.pipeline_services.asset_library.classify import (
    build_classify_prompt,
    create_classify_fn,
    FOOD_CATEGORY_NAMES,
)
from packages.pipeline_services.asset_library.vision_client import (
    build_vision_prompt,
    VisionClient,
)
from packages.provider_config.app_config import AppConfigManager


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
# AppConfigManager.get_categories()
# ---------------------------------------------------------------------------


class TestAppConfigCategories:
    def test_get_categories_default(self) -> None:
        """Empty config should return the default food categories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AppConfigManager(config_dir=tmpdir)
            cats = manager.get_categories()
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
                json.dumps({"asset_library": {"categories": custom_cats}}, ensure_ascii=False),
                encoding="utf-8",
            )
            manager = AppConfigManager(config_dir=tmpdir)
            cats = manager.get_categories()
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
            manager = AppConfigManager(config_dir=tmpdir)
            cats = manager.get_categories()
            assert len(cats) == 10  # fallback to defaults
            assert cats[0].name == "产地溯源"

    def test_get_category_suggestion_model_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AppConfigManager(config_dir=tmpdir)
            assert manager.get_category_suggestion_model() == "deepseek-v4-flash"

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
            manager = AppConfigManager(config_dir=tmpdir)
            assert manager.get_category_suggestion_model() == "custom-model"

    def test_get_category_suggestion_sample_size_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AppConfigManager(config_dir=tmpdir)
            assert manager.get_category_suggestion_sample_size() == 20

    def test_get_asset_library_config_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AppConfigManager(config_dir=tmpdir)
            cfg = manager.get_asset_library_config()
            assert "categories" in cfg
            assert "category_suggestion_model" in cfg
            assert cfg["category_suggestion_model"] == "deepseek-v4-flash"
            assert cfg["category_suggestion_sample_size"] == 20


# ---------------------------------------------------------------------------
# classify.py — configurable prompt and function
# ---------------------------------------------------------------------------


class TestClassifyPrompt:
    def test_build_prompt_default(self) -> None:
        prompt = build_classify_prompt()
        for name in FOOD_CATEGORY_NAMES:
            assert name in prompt, f"Missing {name} in default prompt"

    def test_build_prompt_custom(self) -> None:
        prompt = build_classify_prompt(["采收采集", "加工处理"])
        assert "采收采集" in prompt
        assert "加工处理" in prompt
        assert "产地溯源" not in prompt

    def test_build_prompt_empty_fallback(self) -> None:
        """Empty list should fall back to default food categories."""
        prompt = build_classify_prompt([])
        for name in FOOD_CATEGORY_NAMES:
            assert name in prompt, f"Missing {name} in fallback prompt"

    def test_build_prompt_none_fallback(self) -> None:
        prompt = build_classify_prompt(None)
        for name in FOOD_CATEGORY_NAMES:
            assert name in prompt, f"Missing {name} in fallback prompt"


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
    """Test that create_classify_fn still works without category_names."""

    def test_old_classify_still_works(self) -> None:
        """Without category_names, should use legacy food categories."""
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
        assert isinstance(record.category, Category)

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
        from packages.pipeline_services.asset_library.models import Category as OldCategory

        assert OldCategory is Category

    def test_new_import_works(self) -> None:
        """New imports like ``from ...category_config import CategoryConfig`` work."""
        from packages.pipeline_services.asset_library.category_config import CategoryConfig

        assert CategoryConfig is not None


# ---------------------------------------------------------------------------
# Empty categories edge cases
# ---------------------------------------------------------------------------


class TestEmptyCategories:
    def test_empty_categories_does_not_crash_classify(self) -> None:
        """Empty categories list should not crash create_classify_fn."""
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
            # Empty list falls back to FOOD_CATEGORY_NAMES, so "no_match" is not valid
            result = fn("测试。")
        assert result is None

    def test_empty_categories_does_not_crash_vision(self) -> None:
        """Empty categories list should not crash VisionClient."""
        client = VisionClient(
            api_key="test",
            endpoint="https://api.example.com",
            model="test-model",
            categories=[],
        )
        assert "产地溯源" in client._vision_prompt  # fallback
