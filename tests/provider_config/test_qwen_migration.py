from __future__ import annotations

import tempfile
from pathlib import Path

from packages.provider_config.config_io import save_config as io_save_config
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.tts_config import TTSConfig, TTSConfigManager


class TestQwenMigration:
    def test_mimo_v2_migrates_to_qwen_on_load(self) -> None:
        """加载时 mimo-v2-tts 应被迁移为 qwen3-tts-flash 并持久化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            io_save_config(
                config_path, {"tts": {"model": "mimo-v2-tts", "voice": "old_voice"}}
            )
            reader = ConfigReader(config_dir=tmpdir)
            tts = reader.get_tts_config()
            assert tts["provider"] == "qwen"
            assert tts["model"] == "qwen3-tts-flash"
            assert tts["voice"] == "Rocky"

    def test_mimo_v2_migration_is_idempotent(self) -> None:
        """迁移后的配置重复加载不产生副作用"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            io_save_config(
                config_path, {"tts": {"model": "mimo-v2-tts", "voice": "old_voice"}}
            )
            for _ in range(3):
                reader = ConfigReader(config_dir=tmpdir)
                tts = reader.get_tts_config()
                assert tts["model"] == "qwen3-tts-flash"
                assert tts["voice"] == "Rocky"

    def test_mimo_v2_migration_with_product_config(self) -> None:
        """product 级别的 mimo-v2-tts 也在加载时迁移"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "app_config.json"
            io_save_config(
                config_path,
                {"products": [{"id": "prod-1", "tts": {"model": "mimo-v2-tts"}}]},
            )
            reader = ConfigReader(config_dir=tmpdir)
            tts = reader.get_tts_config(product_id="prod-1")
            assert tts["provider"] == "qwen"
            assert tts["model"] == "qwen3-tts-flash"
            assert tts["voice"] == "Rocky"

    def test_save_config_does_not_rewrite_model(self) -> None:
        """写路径不再隐式改写模型选择"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TTSConfigManager(config_dir=tmpdir)
            config = TTSConfig(model="qwen3-tts-flash", voice="Cherry")
            mgr.save_config(config)
            for _ in range(3):
                result = mgr.get_config()
                assert result.model == "qwen3-tts-flash"
                assert result.voice == "Cherry"
