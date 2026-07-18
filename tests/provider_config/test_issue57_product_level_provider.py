from __future__ import annotations

import tempfile
from pathlib import Path

from packages.provider_config.config_io import load_config, save_config
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.config_reader import ProductStore


def _make_store(tmpdir: str) -> ProductStore:
    config_path = Path(tmpdir) / "app_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    reader = ConfigReader(config_dir=tmpdir)
    return ProductStore(reader=reader, config_path=config_path)


def _config_path(tmpdir: str) -> Path:
    return Path(tmpdir) / "app_config.json"


def _get_tts_config(store: ProductStore) -> dict:
    """Replicate ConfigReader.get_tts_config() active-product resolution."""
    store._reader.reload()
    active_id = store._reader.active_product_id
    if active_id:
        return store._reader.get_tts_config(product_id=active_id)
    return store._reader.get_tts_config()


def _get_llm_config(store: ProductStore) -> dict:
    store._reader.reload()
    active_id = store._reader.active_product_id
    if active_id:
        return store._reader.get_llm_config(product_id=active_id)
    return store._reader.get_llm_config()


def _get_vision_config(store: ProductStore) -> dict:
    store._reader.reload()
    active_id = store._reader.active_product_id
    if active_id:
        return store._reader.get_vision_config(product_id=active_id)
    return store._reader.get_vision_config()


def _set_tts(tmpdir: str, store: ProductStore, key: str, value) -> None:
    """Replicate ConfigReader.set_tts() logic."""
    path = _config_path(tmpdir)
    raw = load_config(path)
    from packages.provider_config.config_constants import _set_nested

    active_id = raw.get("active_product_id", "")
    if active_id:
        for i, p in enumerate(raw.get("products", [])):
            if p.get("id") == active_id:
                if "tts" not in p:
                    raw["products"][i]["tts"] = {}
                _set_nested(raw["products"][i]["tts"], key, value)
                save_config(path, raw)
                store._reader.reload()
                return
    if "tts" not in raw:
        raw["tts"] = {}
    _set_nested(raw["tts"], key, value)
    save_config(path, raw)
    store._reader.reload()


def _set_vision(tmpdir: str, store: ProductStore, key: str, value) -> None:
    path = _config_path(tmpdir)
    raw = load_config(path)
    from packages.provider_config.config_constants import _set_nested

    active_id = raw.get("active_product_id", "")
    if active_id:
        for i, p in enumerate(raw.get("products", [])):
            if p.get("id") == active_id:
                if "vision" not in p:
                    raw["products"][i]["vision"] = {}
                _set_nested(raw["products"][i]["vision"], key, value)
                save_config(path, raw)
                store._reader.reload()
                return
    if "vision" not in raw:
        raw["vision"] = {}
    _set_nested(raw["vision"], key, value)
    save_config(path, raw)
    store._reader.reload()


class TestProductLevelTTSFallback:
    """get_tts_config() 优先读 product-level tts，无配置时 fallback 到 root-level。"""

    def test_tts_reads_product_level_when_set(self) -> None:
        """产品级 tts 配置应优先生效。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("p1")
            store.save_product_config(
                "p1", {"tts": {"provider": "qwen", "model": "qwen-tts"}}
            )
            config = _get_tts_config(store)
            assert config["provider"] == "qwen"
            assert config["model"] == "qwen-tts"

    def test_tts_falls_back_to_root_when_product_has_no_tts(self) -> None:
        """产品未配置 tts 时回退到 root-level。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            _set_tts(tmpdir, store, "provider", "mimo")
            store.switch_product("p1")
            store.save_product_config("p1", {"default_name": "test"})
            config = _get_tts_config(store)
            assert config["provider"] == "mimo"

    def test_tts_falls_back_to_defaults_when_nothing_configured(self) -> None:
        """root 和 product 都无配置时使用 DEFAULTS。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            config = _get_tts_config(store)
            assert config["provider"] == "qwen"

    def test_tts_product_level_overrides_root(self) -> None:
        """product-level tts 覆盖 root-level tts 的同名字段。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            _set_tts(tmpdir, store, "provider", "mimo")
            _set_tts(tmpdir, store, "model", "mimo-v2.5-tts")
            config = _get_tts_config(store)
            assert config["provider"] == "mimo"

            store.switch_product("p1")
            store.save_product_config("p1", {"tts": {"provider": "qwen"}})
            config = _get_tts_config(store)
            assert config["provider"] == "qwen"  # product 覆盖
            assert config["model"] == "mimo-v2.5-tts"  # 回退到 root

    def test_tts_product_level_deep_merges(self) -> None:
        """product-level tts 与 root 深度合并，保留未覆盖的嵌套默认值。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("p1")
            store.save_product_config(
                "p1",
                {
                    "tts": {
                        "provider": "minimax",
                        "director": {"character": "播客主持人"},
                    }
                },
            )
            config = _get_tts_config(store)
            assert config["provider"] == "minimax"
            assert config["director"]["character"] == "播客主持人"
            # DEFAULTS 中未被覆盖的字段仍保留
            assert config["director"]["scene"] == ""

    def test_tts_no_active_product_reads_root_only(self) -> None:
        """无活跃产品时只读 root-level。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            _set_tts(tmpdir, store, "provider", "mimo")
            config = _get_tts_config(store)
            assert config["provider"] == "mimo"


class TestProductLevelLLMFallback:
    """get_llm_config() 优先读 product-level llm。"""

    def test_llm_reads_product_level_when_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("p1")
            store.save_product_config(
                "p1", {"llm": {"provider": "kimi", "model": "kimi-latest"}}
            )
            config = _get_llm_config(store)
            assert config["provider"] == "kimi"
            assert config["model"] == "kimi-latest"

    def test_llm_falls_back_to_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("p1")
            path = _config_path(tmpdir)
            raw = load_config(path)
            raw["llm"] = {"provider": "openai", "model": "gpt-4o"}
            save_config(path, raw)
            store._reader.reload()
            store.save_product_config("p1", {"default_name": "test"})
            config = _get_llm_config(store)
            assert config["provider"] == "openai"

    def test_llm_product_overrides_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            path = _config_path(tmpdir)
            raw = load_config(path)
            raw["llm"] = {"provider": "deepseek", "model": "deepseek-v4-pro"}
            save_config(path, raw)
            store._reader.reload()
            store.switch_product("p1")
            store.save_product_config("p1", {"llm": {"provider": "kimi"}})
            config = _get_llm_config(store)
            assert config["provider"] == "kimi"
            assert config["model"] == "deepseek-v4-pro"


class TestProductLevelVisionFallback:
    """get_vision_config() 优先读 product-level vision。"""

    def test_vision_reads_product_level_when_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            store.switch_product("p1")
            store.save_product_config(
                "p1", {"vision": {"provider": "openai", "model": "gpt-4o-mini"}}
            )
            config = _get_vision_config(store)
            assert config["provider"] == "openai"
            assert config["model"] == "gpt-4o-mini"

    def test_vision_falls_back_to_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            _set_vision(tmpdir, store, "provider", "claude")
            store.switch_product("p1")
            store.save_product_config("p1", {"default_name": "test"})
            config = _get_vision_config(store)
            assert config["provider"] == "claude"

    def test_vision_product_overrides_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = _make_store(tmpdir)
            _set_vision(tmpdir, store, "provider", "xiaomi")
            _set_vision(tmpdir, store, "model", "mimo-v2.5")
            store.switch_product("p1")
            store.save_product_config("p1", {"vision": {"provider": "openai"}})
            config = _get_vision_config(store)
            assert config["provider"] == "openai"
            assert config["model"] == "mimo-v2.5"
