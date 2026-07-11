"""Tests for packages.provider_config.config_reader."""

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path
from unittest import mock

import pytest

from packages.provider_config.config_reader import ConfigReader


def _write_config(dir_path: str, data: dict) -> Path:
    config_path = Path(dir_path) / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return config_path


# ---------------------------------------------------------------------------
# Seam: constructor migrates + caches
# ---------------------------------------------------------------------------


class TestConstructorMigration:
    def test_migrates_old_product_to_products(self) -> None:
        """旧格式 product 应自动迁移为 products."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = _write_config(tmpdir, {
                "product": {"default_name": "旧产品"},
                "active_product_id": "default",
            })
            reader = ConfigReader(config_dir=tmpdir)

            # After migration, the product should be accessible
            config = reader.get_product_config(product_id="default")
            assert config["default_name"] == "旧产品"

    def test_migration_does_not_overwrite_existing_products(self) -> None:
        """已有 products 时不触发迁移."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = _write_config(tmpdir, {
                "products": [{"id": "snack", "default_name": "零食"}],
                "active_product_id": "snack",
            })
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_product_config(product_id="snack")
            assert config["default_name"] == "零食"

    def test_empty_config_returns_defaults(self) -> None:
        """空配置时返回 DEFAULTS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            tts = reader.get_tts_config()
            assert tts["provider"] == "qwen"


# ---------------------------------------------------------------------------
# Seam: get_tts_config / get_llm_config / get_vision_config
# ---------------------------------------------------------------------------


class TestProviderConfigs:
    def test_get_tts_config_defaults_only(self) -> None:
        """无 root 无 product 配置时只返回 DEFAULTS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_tts_config()
            assert config["provider"] == "qwen"
            assert config["model"] == "qwen-tts"
            assert config["voice"] == "Cherry"

    def test_get_tts_config_root_override(self) -> None:
        """root-level tts 覆盖 DEFAULTS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {"tts": {"voice": "RootVoice"}})
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_tts_config()
            assert config["voice"] == "RootVoice"
            # DEFAULTS still present
            assert config["provider"] == "qwen"

    def test_get_tts_config_with_product_override(self) -> None:
        """product-level tts 覆盖 root + DEFAULTS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "tts": {"voice": "RootVoice"},
                    "products": [
                        {"id": "snack", "tts": {"voice": "ProductVoice"}},
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            # Without product: DEFAULTS + root
            assert reader.get_tts_config()["voice"] == "RootVoice"
            # With product: DEFAULTS + root + product
            assert reader.get_tts_config(product_id="snack")["voice"] == "ProductVoice"

    def test_get_llm_config_three_layer_merge(self) -> None:
        """LLM 配置三层合并正确."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "llm": {"model": "root-model"},
                    "products": [
                        {"id": "snack", "llm": {"thinking": "enabled"}},
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            base = reader.get_llm_config()
            assert base["model"] == "root-model"
            assert base["thinking"] == "disabled"  # DEFAULTS

            prod = reader.get_llm_config(product_id="snack")
            assert prod["model"] == "root-model"  # root
            assert prod["thinking"] == "enabled"  # product override

    def test_get_vision_config_three_layer_merge(self) -> None:
        """Vision 配置三层合并正确."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "vision": {"model": "root-model-vision"},
                    "products": [
                        {"id": "snack", "vision": {"provider": "openai"}},
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            base = reader.get_vision_config()
            assert base["model"] == "root-model-vision"
            assert base["provider"] == "xiaomi"  # DEFAULTS

            prod = reader.get_vision_config(product_id="snack")
            assert prod["provider"] == "openai"
            assert prod["model"] == "root-model-vision"


# ---------------------------------------------------------------------------
# Seam: get_media_config / get_video_config / get_asset_library_config
# ---------------------------------------------------------------------------


class TestNonProductConfigs:
    def test_get_media_config_returns_defaults_and_overrides(self) -> None:
        """get_media_config 合并 DEFAULTS + root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {"media": {"ffmpeg_path": "/custom/ffmpeg"}},
            )
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_media_config()
            assert config["ffmpeg_path"] == "/custom/ffmpeg"
            assert config["subtitle_mode"] == "script_timed"  # DEFAULTS

    def test_get_video_config_returns_defaults_and_overrides(self) -> None:
        """get_video_config 合并 DEFAULTS + root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {"video": {"cover_title_style": {"position": "top"}}},
            )
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_video_config()
            assert config["cover_title_style"]["position"] == "top"
            assert config["cover_title_style"]["primary_color"] == "#FFD700"  # DEFAULTS

    def test_get_asset_library_config_returns_defaults_and_overrides(self) -> None:
        """get_asset_library_config 合并 DEFAULTS + root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {"asset_library": {"category_suggestion_sample_size": 50}},
            )
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_asset_library_config()
            assert config["category_suggestion_sample_size"] == 50
            assert config["category_suggestion_model"] == "deepseek-v4-flash"  # DEFAULTS


# ---------------------------------------------------------------------------
# Seam: get_product_config / get_product_value
# ---------------------------------------------------------------------------


class TestProductConfig:
    def test_get_product_config_no_product(self) -> None:
        """product_id=None 返回 DEFAULTS + root product 配置（不触发迁移）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 同时包含 product 和 products 以避免迁移吞掉 root product
            _write_config(
                tmpdir,
                {
                    "product": {"default_name": "RootProduct"},
                    "products": [{"id": "snack"}],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_product_config()
            assert config["default_name"] == "RootProduct"

    def test_get_product_config_for_specific_product(self) -> None:
        """指定 product_id 返回 DEFAULTS + root-product + product-override."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "product": {"default_brand": "RootBrand"},
                    "products": [
                        {
                            "id": "snack",
                            "default_name": "零食",
                            "default_brand": "SnackBrand",
                        },
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_product_config(product_id="snack")
            assert config["default_name"] == "零食"
            assert config["default_brand"] == "SnackBrand"
            assert config["id"] == "snack"

    def test_get_product_config_product_does_not_exist_returns_root_defaults(self) -> None:
        """product_id 不存在时返回 DEFAULTS + root-product（回退行为）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 同时包含 product 和 products 以避免迁移吞掉 root product
            _write_config(
                tmpdir,
                {
                    "product": {"default_name": "RootProduct"},
                    "products": [{"id": "snack"}],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_product_config(product_id="nonexistent")
            assert config["default_name"] == "RootProduct"

    def test_get_product_value(self) -> None:
        """get_product_value 获取嵌套值."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "products": [
                        {
                            "id": "snack",
                            "script": {"scene": "自定义场景"},
                        },
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            assert reader.get_product_value("script.scene", product_id="snack") == "自定义场景"
            assert reader.get_product_value("script.unknown", "fallback", product_id="snack") == "fallback"


# ---------------------------------------------------------------------------
# Seam: get_scene_config
# ---------------------------------------------------------------------------


class TestSceneConfig:
    def test_get_scene_config_defaults(self) -> None:
        """无任何 scene 配置时返回 DEFAULTS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_scene_config()
            assert config["folders"] == []
            assert config["transition_duration_ms"] == 500

    def test_get_scene_config_product_overrides_top_level(self) -> None:
        """产品级 scene 优先于顶级 scene."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "scene": {
                        "folders": [{"name": "顶级", "path": "top"}],
                        "transition_duration_ms": 300,
                    },
                    "products": [
                        {
                            "id": "snack",
                            "scene": {
                                "folders": [{"name": "产品级", "path": "prod"}],
                                "transition_duration_ms": 600,
                            },
                        },
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            # No product → top-level scene
            base = reader.get_scene_config()
            assert base["folders"][0]["name"] == "顶级"
            assert base["transition_duration_ms"] == 300

            # With product → product-level scene
            prod = reader.get_scene_config(product_id="snack")
            assert prod["folders"][0]["name"] == "产品级"
            assert prod["transition_duration_ms"] == 600

    def test_get_scene_config_product_partial_merge(self) -> None:
        """产品级 scene 部分字段时回退到 DEFAULTS."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "products": [
                        {
                            "id": "snack",
                            "scene": {
                                "folders": [{"name": "单文件夹", "path": "only"}],
                            },
                        },
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            config = reader.get_scene_config(product_id="snack")
            assert config["folders"][0]["name"] == "单文件夹"
            assert config["transition_duration_ms"] == 500  # DEFAULTS


# ---------------------------------------------------------------------------
# Seam: get_keyword_map
# ---------------------------------------------------------------------------


class TestKeywordMap:
    def test_get_keyword_map_returns_product_mapping(self) -> None:
        """返回产品级 keyword_map."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(
                tmpdir,
                {
                    "products": [
                        {
                            "id": "snack",
                            "keyword_map": {"开箱": ["unboxing"], "试吃": ["tasting"]},
                        },
                    ],
                },
            )
            reader = ConfigReader(config_dir=tmpdir)
            km = reader.get_keyword_map(product_id="snack")
            assert km == {"开箱": ["unboxing"], "试吃": ["tasting"]}

    def test_get_keyword_map_empty_when_not_configured(self) -> None:
        """未配置时返回空 dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {})
            reader = ConfigReader(config_dir=tmpdir)
            assert reader.get_keyword_map() == {}


# ---------------------------------------------------------------------------
# Seam: category_suggestion
# ---------------------------------------------------------------------------


class TestCategorySuggestion:
    def test_get_category_suggestion_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {
                "asset_library": {"category_suggestion_model": "custom-model"},
            })
            reader = ConfigReader(config_dir=tmpdir)
            assert reader.get_category_suggestion_model() == "custom-model"

    def test_get_category_suggestion_sample_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {
                "asset_library": {"category_suggestion_sample_size": 100},
            })
            reader = ConfigReader(config_dir=tmpdir)
            assert reader.get_category_suggestion_sample_size() == 100


# ---------------------------------------------------------------------------
# Seam: reload
# ---------------------------------------------------------------------------


class TestReload:
    def test_reload_picks_up_file_changes(self) -> None:
        """reload() 重新读取文件并重建缓存."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = _write_config(tmpdir, {"tts": {"voice": "FirstVoice"}})
            reader = ConfigReader(config_dir=tmpdir)
            assert reader.get_tts_config()["voice"] == "FirstVoice"

            # 直接修改文件
            _write_config(tmpdir, {"tts": {"voice": "SecondVoice"}})
            reader.reload()
            assert reader.get_tts_config()["voice"] == "SecondVoice"

    def test_reload_thread_safe(self) -> None:
        """并发 reload + read 不崩溃."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {"tts": {"voice": "SafeVoice"}})
            reader = ConfigReader(config_dir=tmpdir)
            errors: list[Exception] = []
            barrier = threading.Barrier(6, timeout=5)

            def _reloader() -> None:
                barrier.wait()
                for _ in range(10):
                    try:
                        reader.reload()
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)

            def _reader() -> None:
                barrier.wait()
                for _ in range(10):
                    try:
                        reader.get_tts_config()
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)

            threads = [threading.Thread(target=_reloader if i < 2 else _reader) for i in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert len(errors) == 0


# ---------------------------------------------------------------------------
# Seam: O(1) cache
# ---------------------------------------------------------------------------


class TestCacheBehavior:
    def test_get_tts_config_is_cached(self) -> None:
        """get_tts_config 应返回同一个对象（缓存引用）."""
        with tempfile.TemporaryDirectory() as tmpdir:
            _write_config(tmpdir, {"tts": {"voice": "CachedVoice"}})
            reader = ConfigReader(config_dir=tmpdir)
            first = reader.get_tts_config()
            second = reader.get_tts_config()
            assert first is second
