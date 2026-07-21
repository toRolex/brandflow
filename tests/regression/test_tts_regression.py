"""回归测试：验证已修复的bug不再出现"""

from packages.provider_config.tts_config import TTSConfig, TTSConfigManager


class TestTTSConfigRegression:
    def test_merge_empty_string_does_not_override(self):
        base = TTSConfig(voice_design_prompt="original")
        override = TTSConfig(voice_design_prompt="")
        merged = TTSConfigManager._merge_configs(base, override)
        assert merged.voice_design_prompt == "original"

    def test_merge_empty_list_does_not_override(self):
        base = TTSConfig(random_voices=["A", "B"])
        override = TTSConfig(random_voices=[])
        merged = TTSConfigManager._merge_configs(base, override)
        assert merged.random_voices == ["A", "B"]

    def test_merge_none_does_not_override(self):
        base = TTSConfig(style_prompt="sp")
        override = TTSConfig(style_prompt=None)
        merged = TTSConfigManager._merge_configs(base, override)
        assert merged.style_prompt == "sp"

    def test_project_config_overrides_global(self, tmp_path):
        global_path = tmp_path / "tts_config.json"
        global_path.write_text('{"model": "global", "voice": "GlobalVoice"}')

        project_dir = tmp_path / "projects" / "proj-1"
        project_dir.mkdir(parents=True)
        (project_dir / "tts_config.json").write_text('{"model": "project"}')

        manager = TTSConfigManager(config_dir=str(tmp_path))
        config = manager.get_config(project_id="proj-1")
        assert config.model == "project"
        assert config.voice == "GlobalVoice"

    def test_save_creates_directory_structure(self, tmp_path):
        manager = TTSConfigManager(config_dir=str(tmp_path))
        manager.save_config(TTSConfig(model="test"), project_id="new-project")

        config_path = tmp_path / "projects" / "new-project" / "tts_config.json"
        assert config_path.exists()

    def test_with_defaults_fills_none_values(self):
        config = TTSConfig(model="custom")
        with_defaults = config.with_defaults()
        assert with_defaults.model == "custom"
        assert with_defaults.voice == "Cherry"
        assert with_defaults.fallback_voice == "Stella"
