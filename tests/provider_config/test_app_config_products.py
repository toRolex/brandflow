from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packages.provider_config.config_io import load_config
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.product_store import ProductStore


def _make_store(tmpdir: str) -> ProductStore:
    config_path = Path(tmpdir) / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    reader = ConfigReader(config_dir=tmpdir)
    return ProductStore(reader=reader, config_path=config_path)


def test_list_products_empty() -> None:
    """无产品时 list_products 返回空列表。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        assert store.list_products() == []


def test_switch_product_creates_and_sets_active() -> None:
    """switch_product 应创建产品并设为活跃。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.switch_product("prod_001")

        products = store.list_products()
        assert len(products) == 1
        assert products[0]["id"] == "prod_001"

        raw = load_config(store._reader._config_path)
        assert raw["active_product_id"] == "prod_001"


def test_get_product_config_active() -> None:
    """get_product_config() 返回当前活跃产品配置。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.switch_product("prod_001")
        store.set_product("default_name", "羊肚菌")

        config = store.get_product_config()
        assert config["default_name"] == "羊肚菌"
        assert config["id"] == "prod_001"
        assert config["name"] == "羊肚菌"


def test_get_product_config_by_id() -> None:
    """get_product_config(product_id) 返回指定产品配置。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.switch_product("prod_001")
        store.set_product("default_name", "羊肚菌")
        store.switch_product("prod_002")
        store.set_product("default_name", "竹荪")

        assert store.get_product_config("prod_001")["default_name"] == "羊肚菌"
        assert store.get_product_config("prod_002")["default_name"] == "竹荪"


def test_save_product_config_updates_target_only() -> None:
    """save_product_config 只更新目标产品，不切换活跃产品。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.switch_product("prod_001")
        store.set_product("default_name", "羊肚菌")
        store.switch_product("prod_002")
        store.set_product("default_name", "竹荪")

        store.save_product_config("prod_001", {"default_name": "羊肚菌尊享版"})

        # 活跃产品仍为 prod_002
        assert store.get_product_config()["default_name"] == "竹荪"
        # prod_001 已被修改
        assert store.get_product_config("prod_001")["default_name"] == "羊肚菌尊享版"


def test_save_product_config_creates_missing_product() -> None:
    """save_product_config 对产品不存在时创建它。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.switch_product("prod_001")

        store.save_product_config("prod_002", {"default_name": "竹荪"})

        assert len(store.list_products()) == 2
        assert store.get_product_config("prod_002")["default_name"] == "竹荪"


def test_backward_compatibility_migration() -> None:
    """旧格式 product 单一段自动迁移为 products + active_product_id。"""
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

        store = _make_store(tmpdir)
        products = store.list_products()
        assert len(products) == 1
        assert products[0]["id"] == "default"
        assert products[0]["name"] == "羊肚菌"

        config = store.get_product_config()
        assert config["default_name"] == "羊肚菌"
        assert config["default_brand"] == "菌王"
        assert config["script"]["scene"] == "食材展示"
        # DEFAULTS 仍然生效
        assert config["script"]["word_count_min"] == 150

        raw = json.loads(config_path.read_text(encoding="utf-8"))
        assert "product" not in raw
        assert "products" in raw
        assert raw["active_product_id"] == "default"


def test_product_config_isolation() -> None:
    """产品 A 的修改不应影响产品 B。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.switch_product("prod_a")
        store.set_product("default_name", "产品 A")
        store.set_product("default_brand", "品牌 A")

        store.switch_product("prod_b")
        store.set_product("default_name", "产品 B")
        store.set_product("default_brand", "品牌 B")

        assert store.get_product_config("prod_a")["default_name"] == "产品 A"
        assert store.get_product_config("prod_a")["default_brand"] == "品牌 A"
        assert store.get_product_config("prod_b")["default_name"] == "产品 B"
        assert store.get_product_config("prod_b")["default_brand"] == "品牌 B"


def test_reset_product_config_updates_active_when_removed() -> None:
    """删除活跃产品后，活跃产品应切换到剩余产品。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.switch_product("prod_001")
        store.switch_product("prod_002")
        store.reset_product_config()

        assert len(store.list_products()) == 1
        assert load_config(store._reader._config_path)["active_product_id"] == "prod_001"
