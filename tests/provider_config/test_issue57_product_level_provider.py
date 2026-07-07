from __future__ import annotations

import tempfile

from packages.provider_config.app_config import AppConfigManager


class TestProductLevelTTSFallback:
    """get_tts_config() 优先读 product-level tts，无配置时 fallback 到 root-level。"""

    def test_tts_reads_product_level_when_set(self) -> None:
        """产品级 tts 配置应优先生效。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.switch_product("p1")
            # 写入产品级 tts 配置
            mgr.save_product_config("p1", {
                "tts": {"provider": "qwen", "model": "qwen-tts"}
            })
            config = mgr.get_tts_config()
            assert config["provider"] == "qwen"
            assert config["model"] == "qwen-tts"

    def test_tts_falls_back_to_root_when_product_has_no_tts(self) -> None:
        """产品未配置 tts 时回退到 root-level。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.set_tts("provider", "mimo")
            mgr.switch_product("p1")
            mgr.save_product_config("p1", {"default_name": "test"})
            config = mgr.get_tts_config()
            assert config["provider"] == "mimo"

    def test_tts_falls_back_to_defaults_when_nothing_configured(self) -> None:
        """root 和 product 都无配置时使用 DEFAULTS。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            config = mgr.get_tts_config()
            assert config["provider"] == "qwen"

    def test_tts_product_level_overrides_root(self) -> None:
        """product-level tts 覆盖 root-level tts 的同名字段。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.set_tts("provider", "mimo")
            mgr.set_tts("model", "mimo-v2.5-tts")
            # 确保 root-level 已被持久化
            assert mgr.get_tts_value("provider") == "mimo"

            mgr.switch_product("p1")
            mgr.save_product_config("p1", {
                "tts": {"provider": "qwen"}
            })
            config = mgr.get_tts_config()
            assert config["provider"] == "qwen"  # product 覆盖
            assert config["model"] == "mimo-v2.5-tts"  # 回退到 root

    def test_tts_product_level_deep_merges(self) -> None:
        """product-level tts 与 root 深度合并，保留未覆盖的嵌套默认值。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.switch_product("p1")
            mgr.save_product_config("p1", {
                "tts": {
                    "provider": "minimax",
                    "director": {"character": "播客主持人"}
                }
            })
            config = mgr.get_tts_config()
            assert config["provider"] == "minimax"
            assert config["director"]["character"] == "播客主持人"
            # DEFAULTS 中未被覆盖的字段仍保留
            assert config["director"]["scene"] == ""

    def test_tts_no_active_product_reads_root_only(self) -> None:
        """无活跃产品时只读 root-level。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.set_tts("provider", "mimo")
            config = mgr.get_tts_config()
            assert config["provider"] == "mimo"


class TestProductLevelLLMFallback:
    """get_llm_config() 优先读 product-level llm。"""

    def test_llm_reads_product_level_when_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.switch_product("p1")
            mgr.save_product_config("p1", {
                "llm": {"provider": "kimi", "model": "kimi-latest"}
            })
            config = mgr.get_llm_config()
            assert config["provider"] == "kimi"
            assert config["model"] == "kimi-latest"

    def test_llm_falls_back_to_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.switch_product("p1")
            # root 有自定义值
            raw = mgr._load()
            raw["llm"] = {"provider": "openai", "model": "gpt-4o"}
            mgr._save(raw)
            mgr.save_product_config("p1", {"default_name": "test"})
            config = mgr.get_llm_config()
            assert config["provider"] == "openai"

    def test_llm_product_overrides_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            raw = mgr._load()
            raw["llm"] = {"provider": "deepseek", "model": "deepseek-v4-pro"}
            mgr._save(raw)
            mgr.switch_product("p1")
            mgr.save_product_config("p1", {
                "llm": {"provider": "kimi"}
            })
            config = mgr.get_llm_config()
            assert config["provider"] == "kimi"
            assert config["model"] == "deepseek-v4-pro"


class TestProductLevelVisionFallback:
    """get_vision_config() 优先读 product-level vision。"""

    def test_vision_reads_product_level_when_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.switch_product("p1")
            mgr.save_product_config("p1", {
                "vision": {"provider": "openai", "model": "gpt-4o-mini"}
            })
            config = mgr.get_vision_config()
            assert config["provider"] == "openai"
            assert config["model"] == "gpt-4o-mini"

    def test_vision_falls_back_to_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.set_vision("provider", "claude")
            mgr.switch_product("p1")
            mgr.save_product_config("p1", {"default_name": "test"})
            config = mgr.get_vision_config()
            assert config["provider"] == "claude"

    def test_vision_product_overrides_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AppConfigManager(config_dir=tmpdir)
            mgr.set_vision("provider", "xiaomi")
            mgr.set_vision("model", "mimo-v2.5")
            mgr.switch_product("p1")
            mgr.save_product_config("p1", {
                "vision": {"provider": "openai"}
            })
            config = mgr.get_vision_config()
            assert config["provider"] == "openai"
            assert config["model"] == "mimo-v2.5"
