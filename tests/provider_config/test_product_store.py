"""Tests for packages.provider_config.product_store."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.product_store import ProductStore


def _make_store(tmpdir: str) -> ProductStore:
    """Helper: create a ProductStore with a real ConfigReader and config_path."""
    config_path = Path(tmpdir) / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    reader = ConfigReader(config_dir=tmpdir)
    return ProductStore(reader=reader, config_path=config_path)


# ---------------------------------------------------------------------------
# Seam 1: Constructor + active_id
# ---------------------------------------------------------------------------


class TestInit:
    def test_active_id_returns_empty_when_no_products(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            assert store.active_id == ""

    def test_active_id_returns_active_product_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            assert store.active_id == "羊肚菌"


# ---------------------------------------------------------------------------
# Seam 12: _ensure_active_product
# ---------------------------------------------------------------------------


class TestEnsureActiveProduct:
    def test_ensure_creates_default_when_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            raw: dict = {}
            store._ensure_active_product(raw)
            assert raw["products"] == [{"id": "default"}]
            assert raw["active_product_id"] == "default"

    def test_ensure_picks_first_when_no_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            raw = {"products": [{"id": "prod_a"}, {"id": "prod_b"}]}
            store._ensure_active_product(raw)
            assert raw["active_product_id"] == "prod_a"

    def test_ensure_preserves_existing_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            raw = {
                "products": [{"id": "prod_a"}, {"id": "prod_b"}],
                "active_product_id": "prod_b",
            }
            store._ensure_active_product(raw)
            assert raw["active_product_id"] == "prod_b"


# ---------------------------------------------------------------------------
# Seam 2: create_product
# ---------------------------------------------------------------------------


class TestCreateProduct:
    def test_create_product_generates_id_from_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            result = store.create_product("羊肚菌")
            assert result["id"] == "羊肚菌"
            assert result["name"] == "羊肚菌"

    def test_create_product_appends_to_products_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            products = store.list_products()
            assert any(p["id"] == "羊肚菌" for p in products)
            assert any(p["name"] == "羊肚菌" for p in products)

    def test_create_product_empty_name_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            with pytest.raises(ValueError):
                store.create_product("")

    def test_create_product_whitespace_name_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            with pytest.raises(ValueError):
                store.create_product("   ")

    def test_create_product_sets_default_name_in_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            config = store.get_product_config("羊肚菌")
            assert config["default_name"] == "羊肚菌"

    def test_create_product_does_not_change_active_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_a")
            store.create_product("羊肚菌")
            assert store.active_id == "prod_a"


# ---------------------------------------------------------------------------
# Seam 6: list_products
# ---------------------------------------------------------------------------


class TestListProducts:
    def test_list_products_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            assert store.list_products() == []

    def test_list_products_returns_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_001")
            store.set_product("default_name", "羊肚菌")
            store.switch_product("prod_002")
            store.set_product("default_name", "竹荪")

            products = store.list_products()
            assert len(products) == 2
            p1 = next(p for p in products if p["id"] == "prod_001")
            assert p1["name"] == "羊肚菌"
            p2 = next(p for p in products if p["id"] == "prod_002")
            assert p2["name"] == "竹荪"


# ---------------------------------------------------------------------------
# Seam 3: rename_product
# ---------------------------------------------------------------------------


class TestRenameProduct:
    def test_rename_preserves_product_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            result = store.rename_product("羊肚菌", "新鲜羊肚菌")
            assert result["id"] == "羊肚菌"
            assert result["name"] == "新鲜羊肚菌"
            config = store.get_product_config("羊肚菌")
            assert config["default_name"] == "新鲜羊肚菌"

    def test_rename_does_not_affect_active_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_a")
            store.create_product("羊肚菌")
            store.rename_product("羊肚菌", "新鲜羊肚菌")
            assert store.active_id == "prod_a"

    def test_rename_nonexistent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            with pytest.raises(ValueError, match="not found"):
                store.rename_product("nonexistent", "新名称")

    def test_rename_empty_name_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            with pytest.raises(ValueError):
                store.rename_product("羊肚菌", "")

    def test_rename_whitespace_name_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            with pytest.raises(ValueError):
                store.rename_product("羊肚菌", "   ")

    def test_rename_reloads_reader_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.rename_product("羊肚菌", "新鲜羊肚菌")
            assert store._reader.get_product_config("羊肚菌")["default_name"] == "新鲜羊肚菌"


# ---------------------------------------------------------------------------
# Seam 4: delete_product
# ---------------------------------------------------------------------------


class TestDeleteProduct:
    def test_delete_removes_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.delete_product("羊肚菌")
            products = store.list_products()
            assert not any(p["id"] == "羊肚菌" for p in products)

    def test_delete_nonexistent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            with pytest.raises(ValueError, match="not found"):
                store.delete_product("nonexistent")

    def test_delete_active_product_resets_active_to_first_remaining(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("prod_a")
            store.create_product("prod_b")
            store.create_product("prod_c")
            store.switch_product("prod_b")
            result = store.delete_product("prod_b")
            assert result["status"] == "deleted"
            assert result["active_product_id"] in ("prod_a", "prod_c")
            assert store.active_id != "prod_b"

    def test_delete_last_product_clears_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            result = store.delete_product("羊肚菌")
            assert result["status"] == "deleted"
            assert result["active_product_id"] == ""
            assert store.active_id == ""

    def test_delete_non_active_product_does_not_change_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("prod_a")
            store.create_product("prod_b")
            store.switch_product("prod_a")
            result = store.delete_product("prod_b")
            assert result["status"] == "deleted"
            assert result["active_product_id"] == "prod_a"
            assert store.active_id == "prod_a"

    def test_delete_reloads_reader_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.delete_product("羊肚菌")
            assert store._reader.active_product_id == ""


# ---------------------------------------------------------------------------
# Seam 5: switch_product
# ---------------------------------------------------------------------------


class TestSwitchProduct:
    def test_switch_creates_and_sets_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_001")
            products = store.list_products()
            assert len(products) == 1
            assert products[0]["id"] == "prod_001"
            assert store.active_id == "prod_001"

    def test_switch_switches_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_001")
            store.set_product("default_name", "羊肚菌")
            store.switch_product("prod_002")
            store.set_product("default_name", "竹荪")
            config = store.get_product_config()
            assert config["default_name"] == "竹荪"

    def test_switch_existing_does_not_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_001")
            store.switch_product("prod_002")
            store.switch_product("prod_001")
            assert len(store.list_products()) == 2


# ---------------------------------------------------------------------------
# Seam 7: resolve_product_name
# ---------------------------------------------------------------------------


class TestResolveProductName:
    def test_resolve_returns_explicit_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            assert store.resolve_product_name("手工指定") == "手工指定"

    def test_resolve_returns_active_product_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.set_product_config({"default_name": "鲜活羊肚菌"})
            assert store.resolve_product_name() == "鲜活羊肚菌"

    def test_resolve_returns_default_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            assert store.resolve_product_name() == "羊肚菌"

    def test_resolve_returns_id_when_no_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("bare_id")
            assert store.resolve_product_name() == "bare_id"

    def test_resolve_returns_empty_when_no_active_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            assert store.resolve_product_name() == ""


# ---------------------------------------------------------------------------
# Seam 8: set_product_config
# ---------------------------------------------------------------------------


class TestSetProductConfig:
    def test_set_product_config_updates_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.set_product_config({"default_name": "新鲜羊肚菌", "default_brand": "菌王"})
            config = store.get_product_config()
            assert config["default_name"] == "新鲜羊肚菌"
            assert config["default_brand"] == "菌王"

    def test_set_product_config_preserves_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.set_product_config({"default_name": "新鲜羊肚菌"})
            assert store.active_id == "羊肚菌"


# ---------------------------------------------------------------------------
# Seam 9: save_product_config
# ---------------------------------------------------------------------------


class TestSaveProductConfig:
    def test_save_updates_target_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_001")
            store.set_product("default_name", "羊肚菌")
            store.switch_product("prod_002")
            store.set_product("default_name", "竹荪")
            store.save_product_config("prod_001", {"default_name": "羊肚菌尊享版"})
            assert store.get_product_config()["default_name"] == "竹荪"
            assert store.get_product_config("prod_001")["default_name"] == "羊肚菌尊享版"

    def test_save_creates_missing_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_001")
            store.save_product_config("prod_002", {"default_name": "竹荪"})
            assert len(store.list_products()) == 2
            assert store.get_product_config("prod_002")["default_name"] == "竹荪"


# ---------------------------------------------------------------------------
# Seam 10: reset_product_config
# ---------------------------------------------------------------------------


class TestResetProductConfig:
    def test_reset_removes_active_product(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.reset_product_config()
            assert store.active_id == ""

    def test_reset_switches_to_remaining(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_001")
            store.switch_product("prod_002")
            store.reset_product_config()
            assert len(store.list_products()) == 1
            assert store.active_id == "prod_001"

    def test_reset_on_last_product_clears_all(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.reset_product_config()
            assert store.list_products() == []


# ---------------------------------------------------------------------------
# Seam 11: set_product
# ---------------------------------------------------------------------------


class TestSetProduct:
    def test_set_product_writes_nested(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.set_product("script.scene", "食材展示")
            config = store.get_product_config()
            assert config["script"]["scene"] == "食材展示"

    def test_set_product_default_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.set_product("default_name", "顶级羊肚菌")
            config = store.get_product_config()
            assert config["default_name"] == "顶级羊肚菌"

    def test_set_product_reloads_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.create_product("羊肚菌")
            store.set_product("default_name", "顶级羊肚菌")
            assert store._reader.get_product_config("羊肚菌")["default_name"] == "顶级羊肚菌"


# ---------------------------------------------------------------------------
# Seam 13: Backward compatibility via AppConfigManager
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_get_product_config_with_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("prod_001")
            store.set_product("default_name", "羊肚菌")
            store.switch_product("prod_002")
            store.set_product("default_name", "竹荪")
            assert store.get_product_config("prod_001")["default_name"] == "羊肚菌"
            assert store.get_product_config("prod_002")["default_name"] == "竹荪"

    def test_product_config_isolation(self) -> None:
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
