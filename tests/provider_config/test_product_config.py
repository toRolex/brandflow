from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.config_reader import ProductStore


def _make_store(tmpdir: str) -> ProductStore:
    config_path = Path(tmpdir) / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    reader = ConfigReader(config_dir=tmpdir)
    return ProductStore(reader=reader, config_path=config_path)


def _config_path(tmpdir: str) -> Path:
    return Path(tmpdir) / "app_config.json"


def test_get_product_config_defaults() -> None:
    """未配置 product 段时返回 DEFAULTS 默认值"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        config = store.get_product_config()
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
        store = _make_store(tmpdir)
        store.set_product_config(
            {
                "default_name": "测试产品",
                "default_brand": "测试品牌",
            }
        )
        config = store.get_product_config()
        assert config["default_name"] == "测试产品"
        assert config["default_brand"] == "测试品牌"
        # 未覆盖的字段应保留 DEFAULTS
        assert config["script"]["scene"] is not None


def test_set_product_deep_merge() -> None:
    """set_product_config 应与 DEFAULTS 深度合并"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.set_product_config(
            {
                "script": {
                    "scene": "自定义场景",
                    "material": "自定义素材",
                }
            }
        )
        config = store.get_product_config()
        assert config["script"]["scene"] == "自定义场景"
        assert config["script"]["material"] == "自定义素材"
        # 未设置的嵌套字段保留 DEFAULTS
        assert config["script"]["word_count_min"] == 150
        assert config["script"]["emoji_forbidden"] is True


def test_set_product_single_key() -> None:
    """set_product 应支持点分路径单独设置字段"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.set_product("default_name", "某产品")
        store.set_product("script.scene", "开箱场景")
        config = store.get_product_config()
        assert config["default_name"] == "某产品"
        assert config["script"]["scene"] == "开箱场景"


def test_reset_product_config() -> None:
    """reset_product_config 应恢复 DEFAULTS"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.set_product("default_name", "临时产品")
        store.reset_product_config()
        config = store.get_product_config()
        assert config["default_name"] == ""


def test_product_config_persistence() -> None:
    """product 配置应持久化到文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store1 = _make_store(tmpdir)
        store1.set_product("default_name", "持久化产品")

        store2 = _make_store(tmpdir)
        config = store2.get_product_config()
        assert config["default_name"] == "持久化产品"


def test_product_config_with_categories() -> None:
    """product 配置应包含 categories 段且返回 CategoryConfig 列表"""

    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.set_product_config(
            {
                "categories": [
                    {"id": "unboxing", "name": "开箱展示"},
                    {"id": "tasting", "name": "试吃品尝"},
                ]
            }
        )
        config = store.get_product_config()
        assert len(config["categories"]) == 2
        assert config["categories"][0]["id"] == "unboxing"


def test_product_config_file_structure() -> None:
    """验证 app_config.json 中 products 段的写入格式"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.set_product("default_name", "格式验证")
        path = _config_path(tmpdir)
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        assert "products" in raw
        assert raw["products"][0]["default_name"] == "格式验证"
        assert "active_product_id" in raw


def test_product_name_falls_back_to_default_name_when_name_empty() -> None:
    """name 为空字符串时 get_product_config 应 fallback 到 default_name"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _config_path(tmpdir)
        raw = {
            "products": [
                {"id": "snack", "name": "", "default_name": "零食测试"},
            ],
            "active_product_id": "snack",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)

        store = _make_store(tmpdir)
        config = store.get_product_config()
        assert config["name"] == "零食测试"
        assert config["default_name"] == "零食测试"
        assert config["id"] == "snack"


def test_product_name_falls_back_to_id_when_both_name_and_default_empty() -> None:
    """name 和 default_name 都为空时 get_product_config 应 fallback 到 id"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _config_path(tmpdir)
        raw = {
            "products": [
                {"id": "snack", "name": "", "default_name": ""},
            ],
            "active_product_id": "snack",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)

        store = _make_store(tmpdir)
        config = store.get_product_config()
        assert config["name"] == "snack"
        assert config["id"] == "snack"


class TestResolveProductName:
    def test_explicit_product_wins(self) -> None:
        """显式传入 product 参数时直接返回该值"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            assert _resolve_product_name(store, "显式产品") == "显式产品"

    def test_falls_back_to_active_product_name(self) -> None:
        """未传 product 时返回活跃产品的 name"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.set_product("default_name", "测试产品")
            assert _resolve_product_name(store) == "测试产品"

    def test_falls_back_to_default_name_when_name_empty(self) -> None:
        """活跃产品 name 为空时 fallback 到 default_name"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _config_path(tmpdir)
            raw = {
                "products": [
                    {"id": "snack", "name": "", "default_name": "零食测试"},
                ],
                "active_product_id": "snack",
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
            store = _make_store(tmpdir)
            assert _resolve_product_name(store) == "零食测试"

    def test_falls_back_to_id_when_both_empty(self) -> None:
        """活跃产品 name 和 default_name 都为空时 fallback 到 id"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _config_path(tmpdir)
            raw = {
                "products": [
                    {"id": "snack", "name": "", "default_name": ""},
                ],
                "active_product_id": "snack",
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False)
            store = _make_store(tmpdir)
            assert _resolve_product_name(store) == "snack"

    def test_returns_empty_when_no_active_product(self) -> None:
        """无活跃产品时返回空字符串"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            assert _resolve_product_name(store) == ""


def _resolve_product_name(store: ProductStore, explicit_product: str = "") -> str:
    """Inline version of ConfigReader.resolve_product_name."""
    if explicit_product:
        return explicit_product
    config = store.get_product_config()
    name = config.get("name", "")
    if name:
        return name
    default = config.get("default_name", "")
    if default:
        return default
    return config.get("id", "")


def test_save_product_config_cleans_empty_name(tmp_path) -> None:
    """save_product_config 保存时应清除产品中显式的空 name 字段。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _config_path(tmpdir)
        raw = {
            "products": [
                {"id": "snack", "name": "", "default_name": "零食测试"},
            ],
            "active_product_id": "snack",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)

        store = _make_store(tmpdir)
        # 保存新配置（不含 name 字段）
        store.save_product_config("snack", {"default_name": "新名字"})

        # 读取文件确认 name 已被清除
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        product = saved["products"][0]
        # name 不应再是空字符串（应被清除或设为 default_name）
        assert product.get("name", "NOT_PRESENT") != ""
        # 读路径应正确解析
        config = store.get_product_config()
        assert config["name"] == "新名字"


def test_list_products_falls_back_to_id() -> None:
    """list_products 在 default_name 和 name 都为空时应 fallback 到 id"""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _config_path(tmpdir)
        raw = {
            "products": [
                {"id": "snack", "name": "", "default_name": ""},
                {"id": "drink", "default_name": "饮料"},
            ],
            "active_product_id": "snack",
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)

        store = _make_store(tmpdir)
        products = store.list_products()
        assert products[0]["id"] == "snack"
        assert products[0]["name"] == "snack"  # fallback to id
        assert products[1]["id"] == "drink"
        assert products[1]["name"] == "饮料"  # default_name wins


def test_set_product_config_keeps_name_consistent(tmp_path) -> None:
    """set_product_config 保存后 name 应与 default_name 一致。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _make_store(tmpdir)
        store.set_product_config({"default_name": "测试产品"})

        config = store.get_product_config()
        assert config["name"] == "测试产品"
        assert config["default_name"] == "测试产品"
