from __future__ import annotations

import tempfile

from packages.provider_config.tts_config import TTSConfig, TTSConfigManager


class TestQwenMigration:
    def test_mimo_v2_migrates_to_qwen_on_save(self) -> None:
        """save_config 时 mimo-v2-tts 应被持久化为 qwen3-tts-flash"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TTSConfigManager(config_dir=tmpdir)
            config = TTSConfig(model="mimo-v2-tts", voice="old_voice")
            mgr.save_config(config)
            # 回读验证迁移已持久化
            loaded = mgr.get_config()
            assert loaded.model == "qwen3-tts-flash"
            assert loaded.voice == "Rocky"

    def test_get_config_no_longer_mutates_on_read(self) -> None:
        """get_config 不应再触发迁移日志"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TTSConfigManager(config_dir=tmpdir)
            config = TTSConfig(model="qwen3-tts-flash", voice="Cherry")
            mgr.save_config(config)
            # 多次读取不应产生迁移副作用
            for _ in range(3):
                result = mgr.get_config()
                assert result.model == "qwen3-tts-flash"
                assert result.voice == "Cherry"

    def test_mimo_v2_migration_with_product_config(self) -> None:
        """save_config 时 product 级别的 mimo-v2-tts 也应被迁移"""
        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = TTSConfigManager(config_dir=tmpdir)
            config = TTSConfig(model="mimo-v2-tts", voice="old_voice")
            mgr.save_config(config, product_id="prod-1")
            loaded = mgr.get_config(product_id="prod-1")
            assert loaded.model == "qwen3-tts-flash"
            assert loaded.voice == "Rocky"
