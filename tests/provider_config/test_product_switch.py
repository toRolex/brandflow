from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packages.provider_config.app_config import AppConfigManager


def test_list_products_empty() -> None:
    """无产品配置时返回空列表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        products = manager.list_products()
        assert products == []


def test_switch_product_creates_new() -> None:
    """切换不存在的产品时应自动创建"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        products = manager.list_products()
        assert len(products) == 1
        assert products[0]["id"] == "prod_001"


def test_get_product_config_with_id() -> None:
    """get_product_config(product_id) 应返回该产品配置"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        manager.set_product("default_name", "羊肚菌")
        manager.switch_product("prod_002")
        manager.set_product("default_name", "竹荪")

        config = manager.get_product_config("prod_001")
        assert config["default_name"] == "羊肚菌"

        config2 = manager.get_product_config("prod_002")
        assert config2["default_name"] == "竹荪"


def test_get_product_config_active() -> None:
    """get_product_config() 无参应返回活跃产品配置"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        manager.set_product("default_name", "羊肚菌")

        config = manager.get_product_config()
        assert config["default_name"] == "羊肚菌"


def test_switch_product_switches_active() -> None:
    """switch_product 应更改活跃产品"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        manager.set_product("default_name", "羊肚菌")
        manager.switch_product("prod_002")
        manager.set_product("default_name", "竹荪")

        # Active should be prod_002
        config = manager.get_product_config()
        assert config["default_name"] == "竹荪"


def test_list_products_returns_summaries() -> None:
    """list_products 返回 {id, name} 摘要"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        manager.set_product("default_name", "羊肚菌")
        manager.switch_product("prod_002")
        manager.set_product("default_name", "竹荪")

        products = manager.list_products()
        assert len(products) == 2

        p1 = next(p for p in products if p["id"] == "prod_001")
        assert p1["name"] == "羊肚菌"

        p2 = next(p for p in products if p["id"] == "prod_002")
        assert p2["name"] == "竹荪"


def test_backward_compatibility_migration() -> None:
    """旧格式 product 自动迁移到 products 列表"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "app_config.json"
        old_data = {
            "product": {
                "default_name": "羊肚菌",
                "default_brand": "菌王",
                "script": {"scene": "食材展示"},
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f)

        manager = AppConfigManager(config_dir=tmpdir)
        products = manager.list_products()
        assert len(products) == 1
        assert products[0]["id"] == "default"
        assert products[0]["name"] == "羊肚菌"

        # Old product key should be gone
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert "product" not in raw
        assert "products" in raw
        assert "active_product_id" in raw


def test_backward_compatibility_get_product_config() -> None:
    """迁移后 get_product_config 仍返回正确的默认值"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "app_config.json"
        old_data = {
            "product": {
                "default_name": "羊肚菌",
                "default_brand": "菌王",
                "script": {"scene": "食材展示"},
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f)

        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_product_config()
        assert config["default_name"] == "羊肚菌"
        assert config["default_brand"] == "菌王"
        assert config["script"]["scene"] == "食材展示"

        # DEFAULTS should still apply
        assert config["script"]["word_count_min"] == 150


def test_get_product_config_nonexistent_returns_defaults() -> None:
    """不存在的 product_id 应返回 DEFAULTS"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_product_config("nonexistent")
        assert config["default_name"] == ""
        assert "script" in config


def test_get_product_config_default_fields() -> None:
    """get_product_config 应包含 id 和 name 字段"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        manager.set_product("default_name", "羊肚菌")

        config = manager.get_product_config()
        assert config["id"] == "prod_001"
        assert config["name"] == "羊肚菌"


def test_persistence_after_migration() -> None:
    """迁移后的格式应持久化保存"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "app_config.json"
        old_data = {
            "product": {"default_name": "羊肚菌", "default_brand": "菌王"},
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(old_data, f)

        # First load triggers migration
        manager1 = AppConfigManager(config_dir=tmpdir)
        config = manager1.get_product_config()
        assert config["default_name"] == "羊肚菌"

        # Second load sees migrated format
        manager2 = AppConfigManager(config_dir=tmpdir)
        config2 = manager2.get_product_config()
        assert config2["default_name"] == "羊肚菌"
        assert manager2._load().get("active_product_id") == "default"


def test_reset_product_config_clears_active() -> None:
    """reset_product_config 应清除活跃产品"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        manager.set_product("default_name", "羊肚菌")
        manager.reset_product_config()

        # After reset, should return defaults
        config = manager.get_product_config()
        assert config["default_name"] == ""

        # Product should be removed from list
        products = manager.list_products()
        assert len(products) == 0
