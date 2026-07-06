from __future__ import annotations

import json
import tempfile

from packages.provider_config.app_config import AppConfigManager


def test_get_product_config_defaults() -> None:
    """未配置 product 段时返回 DEFAULTS 默认值"""
    worktree = "/Users/rolex/Documents/Codes/githubProject/MyProject/brandflow.feature-phase3-slice1-product-config"
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_product_config()
        assert config["default_name"] == ""
        assert config["default_brand"] == ""
        assert "script" in config
        assert "scene" in config["script"]
        assert "material" in config["script"]
        assert "system_prompt" in config["script"]
        assert config["script"]["word_count_min"] == 150
        assert config["script"]["word_count_max"] == 200
        assert "forbidden_words" in config["script"]
        assert "product" in config["script"]["required_word_count"]
        assert config["script"]["emoji_forbidden"] is True


def test_set_product_config() -> None:
    """写入 product 配置后读取应返回新值"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_product_config({
            "default_name": "测试产品",
            "default_brand": "测试品牌",
        })
        config = manager.get_product_config()
        assert config["default_name"] == "测试产品"
        assert config["default_brand"] == "测试品牌"
        # 未覆盖的字段应保留 DEFAULTS
        assert config["script"]["scene"] is not None


def test_set_product_deep_merge() -> None:
    """set_product_config 应与 DEFAULTS 深度合并"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_product_config({
            "script": {
                "scene": "自定义场景",
                "material": "自定义素材",
            }
        })
        config = manager.get_product_config()
        assert config["script"]["scene"] == "自定义场景"
        assert config["script"]["material"] == "自定义素材"
        # 未设置的嵌套字段保留 DEFAULTS
        assert config["script"]["word_count_min"] == 150
        assert config["script"]["emoji_forbidden"] is True


def test_set_product_single_key() -> None:
    """set_product 应支持点分路径单独设置字段"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_product("default_name", "某产品")
        manager.set_product("script.scene", "开箱场景")
        config = manager.get_product_config()
        assert config["default_name"] == "某产品"
        assert config["script"]["scene"] == "开箱场景"


def test_reset_product_config() -> None:
    """reset_product_config 应恢复 DEFAULTS"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_product("default_name", "临时产品")
        manager.reset_product_config()
        config = manager.get_product_config()
        assert config["default_name"] == ""


def test_product_config_persistence() -> None:
    """product 配置应持久化到文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager1 = AppConfigManager(config_dir=tmpdir)
        manager1.set_product("default_name", "持久化产品")

        manager2 = AppConfigManager(config_dir=tmpdir)
        config = manager2.get_product_config()
        assert config["default_name"] == "持久化产品"


def test_product_config_with_categories() -> None:
    """product 配置应包含 categories 段且返回 CategoryConfig 列表"""
    from packages.pipeline_services.asset_library.category_config import CategoryConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_product_config({
            "categories": [
                {"id": "unboxing", "name": "开箱展示"},
                {"id": "tasting", "name": "试吃品尝"},
            ]
        })
        config = manager.get_product_config()
        assert len(config["categories"]) == 2
        assert config["categories"][0]["id"] == "unboxing"


def test_product_config_file_structure() -> None:
    """验证 app_config.json 中 products 段的写入格式"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_product("default_name", "格式验证")
        config_path = manager.config_path
        with open(config_path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "products" in raw
        assert raw["products"][0]["default_name"] == "格式验证"
        assert "active_product_id" in raw
