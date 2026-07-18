from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.config_reader import ProductStore


def _make_store(tmpdir: str) -> ProductStore:
    """Helper: create a ProductStore with a real ConfigReader and config_path."""
    config_path = Path(tmpdir) / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    reader = ConfigReader(config_dir=tmpdir)
    return ProductStore(reader=reader, config_path=config_path)


class TestCreateProduct:
    """ProductStore.create_product(name) 新建产品。"""

    def test_create_product_generates_id_from_name(self) -> None:
        """create_product 用 name 直接作为 product ID。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            result = store.create_product("羊肚菌")
            assert result["id"] == "羊肚菌"
            assert result["name"] == "羊肚菌"

    def test_create_product_appends_to_products_list(self) -> None:
        """create_product 之后 list_products() 包含该产品。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            products = store.list_products()
            assert any(p["id"] == "羊肚菌" for p in products)
            assert any(p["name"] == "羊肚菌" for p in products)

    def test_create_product_empty_name_raises(self) -> None:
        """空名称抛出 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            with pytest.raises(ValueError):
                store.create_product("")

    def test_create_product_whitespace_name_raises(self) -> None:
        """纯空白名称抛出 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            with pytest.raises(ValueError):
                store.create_product("   ")

    def test_create_product_sets_default_name_in_config(self) -> None:
        """create_product 应把 name 写入产品的 default_name 字段。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            config = store.get_product_config("羊肚菌")
            assert config["default_name"] == "羊肚菌"

    def test_create_product_does_not_change_active_product(self) -> None:
        """create_product 新建产品不应自动切换活跃产品。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_a")
            store.create_product("羊肚菌")
            raw = store._reader._raw
            assert raw["active_product_id"] == "prod_a"


class TestRenameProduct:
    """ProductStore.rename_product(product_id, name) 重命名产品。"""

    def test_rename_preserves_product_id(self) -> None:
        """重命名后产品 ID 不变，default_name 更新。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            result = store.rename_product("羊肚菌", "新鲜羊肚菌")
            assert result["id"] == "羊肚菌"
            assert result["name"] == "新鲜羊肚菌"
            config = store.get_product_config("羊肚菌")
            assert config["default_name"] == "新鲜羊肚菌"

    def test_rename_does_not_affect_active_product(self) -> None:
        """重命名不影响活跃产品 ID。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_a")
            store.create_product("羊肚菌")
            store.rename_product("羊肚菌", "新鲜羊肚菌")
            raw = store._reader._raw
            assert raw["active_product_id"] == "prod_a"

    def test_rename_nonexistent_raises(self) -> None:
        """不存在的产品抛出 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            with pytest.raises(ValueError, match="not found"):
                store.rename_product("nonexistent", "新名称")

    def test_rename_empty_name_raises(self) -> None:
        """空名称抛出 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            with pytest.raises(ValueError):
                store.rename_product("羊肚菌", "")

    def test_rename_whitespace_name_raises(self) -> None:
        """纯空白名称抛出 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            with pytest.raises(ValueError):
                store.rename_product("羊肚菌", "   ")


class TestDeleteProduct:
    """ProductStore.delete_product(product_id) 删除产品。"""

    def test_delete_removes_product(self) -> None:
        """删除后 list_products() 不包含该产品。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.delete_product("羊肚菌")
            products = store.list_products()
            assert not any(p["id"] == "羊肚菌" for p in products)

    def test_delete_nonexistent_raises(self) -> None:
        """不存在的产品抛出 ValueError。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            with pytest.raises(ValueError, match="not found"):
                store.delete_product("nonexistent")

    def test_delete_active_product_resets_active_to_first_remaining(self) -> None:
        """删除活跃产品后 active_product_id 切换为第一个剩余产品。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("prod_a")
            store.create_product("prod_b")
            store.create_product("prod_c")
            store.switch_product("prod_b")

            result = store.delete_product("prod_b")
            assert result["status"] == "deleted"
            assert result["active_product_id"] in ("prod_a", "prod_c")
            raw = store._reader._raw
            assert raw["active_product_id"] != "prod_b"

    def test_delete_last_product_clears_active(self) -> None:
        """删除最后一个产品后 active_product_id 为空字符串。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            result = store.delete_product("羊肚菌")
            assert result["status"] == "deleted"
            assert result["active_product_id"] == ""
            raw = store._reader._raw
            assert raw["active_product_id"] == ""

    def test_delete_non_active_product_does_not_change_active(self) -> None:
        """删除非活跃产品不影响 active_product_id。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("prod_a")
            store.create_product("prod_b")
            store.switch_product("prod_a")

            result = store.delete_product("prod_b")
            assert result["status"] == "deleted"
            assert result["active_product_id"] == "prod_a"
