from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packages.provider_config.tts_config import TTSConfig, TTSConfigManager


# ---------------------------------------------------------------------------
# TTSConfig defaults via with_defaults()
# ---------------------------------------------------------------------------


def test_default_model() -> None:
    assert TTSConfig().with_defaults().model == "qwen3-tts-flash"


def test_default_voice() -> None:
    assert TTSConfig().with_defaults().voice == "Cherry"


def test_default_fallback_voice() -> None:
    assert TTSConfig().with_defaults().fallback_voice == "Stella"


def test_default_randomize_voice() -> None:
    assert TTSConfig().with_defaults().randomize_voice is True


def test_default_random_voices() -> None:
    assert TTSConfig().with_defaults().random_voices == ["Cherry", "Stella"]


def test_default_voice_design_prompt() -> None:
    assert TTSConfig().with_defaults().voice_design_prompt == ""


def test_default_style_prompt() -> None:
    assert TTSConfig().with_defaults().style_prompt == "自然 清晰 适合短视频带货口播"


def test_default_audio_format() -> None:
    assert TTSConfig().with_defaults().audio_format == "wav"


# ---------------------------------------------------------------------------
# TTSConfig custom values
# ---------------------------------------------------------------------------


def test_custom_model() -> None:
    assert TTSConfig(model="custom-model").model == "custom-model"


def test_custom_voice() -> None:
    assert TTSConfig(voice="CustomVoice").voice == "CustomVoice"


def test_custom_random_voices() -> None:
    assert TTSConfig(random_voices=["A", "B", "C"]).random_voices == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# TTSConfig.to_dict
# ---------------------------------------------------------------------------


def test_to_dict_returns_all_fields() -> None:
    config = TTSConfig()
    data = config.to_dict()
    assert len(data) == 20


def test_to_dict_values_match_defaults() -> None:
    config = TTSConfig()
    data = config.to_dict()
    assert data["model"] is None
    assert data["voice"] is None


def test_to_dict_custom_values() -> None:
    config = TTSConfig(model="custom", voice="CustomVoice")
    data = config.to_dict()
    assert data["model"] == "custom"
    assert data["voice"] == "CustomVoice"


# ---------------------------------------------------------------------------
# TTSConfig.from_dict
# ---------------------------------------------------------------------------


def test_from_dict_creates_config() -> None:
    data = {"model": "test-model", "voice": "test-voice"}
    config = TTSConfig.from_dict(data)
    assert config.model == "test-model"
    assert config.voice == "test-voice"


def test_from_dict_partial_data() -> None:
    data = {"model": "test-model"}
    config = TTSConfig.from_dict(data)
    assert config.model == "test-model"
    assert config.voice is None


def test_from_dict_empty_dict() -> None:
    config = TTSConfig.from_dict({})
    assert config.model is None
    assert config.voice is None


def test_roundtrip_to_dict_from_dict() -> None:
    original = TTSConfig(model="test", voice="voice", style_prompt="sp")
    restored = TTSConfig.from_dict(original.to_dict())
    assert restored.model == original.model
    assert restored.voice == original.voice
    assert restored.style_prompt == original.style_prompt


def test_from_dict_ignores_unknown_keys() -> None:
    data = {"model": "test", "unknown_key": "value"}
    config = TTSConfig.from_dict(data)
    assert config.model == "test"
    assert not hasattr(config, "unknown_key")


def test_from_dict_ignores_dead_fields() -> None:
    """from_dict uses .get() so dead field keys in old JSON are silently ignored."""
    from packages.provider_config.tts_config import TTSConfig as TC

    config = TC.from_dict({"sample_rate": 32000, "model": "test"})
    assert config.model == "test"


# ---------------------------------------------------------------------------
# TTSConfig.with_defaults
# ---------------------------------------------------------------------------


def test_with_defaults_fills_none() -> None:
    config = TTSConfig(model="custom")
    with_defaults = config.with_defaults()
    assert with_defaults.model == "custom"
    assert with_defaults.voice == "Cherry"


def test_with_defaults_preserves_set_values() -> None:
    config = TTSConfig(model="custom", voice="CustomVoice")
    with_defaults = config.with_defaults()
    assert with_defaults.model == "custom"
    assert with_defaults.voice == "CustomVoice"


# ---------------------------------------------------------------------------
# TTSConfigManager.get_config
# ---------------------------------------------------------------------------


def test_get_config_returns_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config()
        assert config.model == "qwen3-tts-flash"
        assert config.voice == "Cherry"


def test_save_and_load_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = TTSConfigManager(config_dir=tmpdir)
        original = TTSConfig(model="custom-model", voice="CustomVoice")
        manager.save_config(original)

        loaded = manager.get_config()
        assert loaded.model == "custom-model"
        assert loaded.voice == "CustomVoice"


def test_save_and_load_project_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = TTSConfigManager(config_dir=tmpdir)
        original = TTSConfig(model="project-model")
        manager.save_config(original, project_id="proj-1")

        loaded = manager.get_config(project_id="proj-1")
        assert loaded.model == "project-model"


def test_save_creates_directory_if_needed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = TTSConfigManager(config_dir=tmpdir)
        manager.save_config(TTSConfig(model="test"), project_id="new-project")

        config_path = Path(tmpdir) / "projects" / "new-project" / "tts_config.json"
        assert config_path.exists()


# ---------------------------------------------------------------------------
# TTSConfigManager project config
# ---------------------------------------------------------------------------


def test_project_config_without_global() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        projects_dir = Path(tmpdir) / "projects" / "proj-1"
        projects_dir.mkdir(parents=True)
        (projects_dir / "tts_config.json").write_text(
            json.dumps({"model": "project-only"})
        )

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config(project_id="proj-1")
        assert config.model == "project-only"
        assert config.voice == "Cherry"  # default


def test_project_overrides_global() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        global_path = Path(tmpdir) / "tts_config.json"
        global_path.write_text(
            json.dumps({"model": "global-model", "voice": "GlobalVoice"})
        )

        projects_dir = Path(tmpdir) / "projects" / "proj-1"
        projects_dir.mkdir(parents=True)
        (projects_dir / "tts_config.json").write_text(
            json.dumps({"model": "project-model"})
        )

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config(project_id="proj-1")
        assert config.model == "project-model"  # overridden
        assert config.voice == "GlobalVoice"  # from global


def test_nonexistent_project_uses_global() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        global_path = Path(tmpdir) / "tts_config.json"
        global_path.write_text(json.dumps({"model": "global-model"}))

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config(project_id="nonexistent")
        assert config.model == "global-model"


# ---------------------------------------------------------------------------
# TTSConfigManager._merge_configs
# ---------------------------------------------------------------------------


def test_merge_single_config() -> None:
    merged = TTSConfigManager._merge_configs(TTSConfig(model="test"))
    assert merged.model == "test"


def test_merge_later_overrides_earlier() -> None:
    base = TTSConfig(model="base", voice="BaseVoice")
    override = TTSConfig(model="override")
    merged = TTSConfigManager._merge_configs(base, override)
    assert merged.model == "override"
    assert merged.voice == "BaseVoice"  # not overridden


def test_merge_none_values_not_overridden() -> None:
    base = TTSConfig(style_prompt="sp")
    override = TTSConfig(style_prompt=None)
    merged = TTSConfigManager._merge_configs(base, override)
    assert merged.style_prompt == "sp"  # None does not override


def test_merge_empty_string_not_overridden() -> None:
    base = TTSConfig(voice_design_prompt="original")
    override = TTSConfig(voice_design_prompt="")
    merged = TTSConfigManager._merge_configs(base, override)
    assert merged.voice_design_prompt == "original"  # empty string does not override


def test_merge_empty_list_not_overridden() -> None:
    base = TTSConfig(random_voices=["A", "B"])
    override = TTSConfig(random_voices=[])
    merged = TTSConfigManager._merge_configs(base, override)
    assert merged.random_voices == ["A", "B"]  # empty list does not override


def test_merge_non_empty_overrides_empty() -> None:
    base = TTSConfig(voice_design_prompt="", style_prompt=None)
    override = TTSConfig(voice_design_prompt="new prompt", style_prompt="sp")
    merged = TTSConfigManager._merge_configs(base, override)
    assert merged.voice_design_prompt == "new prompt"
    assert merged.style_prompt == "sp"


def test_merge_false_not_overridden_by_none() -> None:
    base = TTSConfig(randomize_voice=False)
    override = TTSConfig(randomize_voice=None)
    merged = TTSConfigManager._merge_configs(base, override)
    assert merged.randomize_voice is False


def test_merge_multiple_configs() -> None:
    c1 = TTSConfig(model="m1", voice="v1")
    c2 = TTSConfig(model="m2", style_prompt="style2")
    c3 = TTSConfig(model="m3")
    merged = TTSConfigManager._merge_configs(c1, c2, c3)
    assert merged.model == "m3"  # last wins
    assert merged.voice == "v1"  # not overridden
    assert merged.style_prompt == "style2"  # set by c2


# ---------------------------------------------------------------------------
# TTSConfigManager delegates to ConfigReader / save_config
# ---------------------------------------------------------------------------


def test_tts_config_from_app_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from packages.provider_config.config_io import save_config
        from packages.provider_config.config_reader import ConfigReader

        config_path = Path(tmpdir) / "app_config.json"
        save_config(config_path, {"tts": {"model": "from-app-config"}})

        reader = ConfigReader(config_dir=tmpdir)
        assert reader.get_tts_config()["model"] == "from-app-config"

        tts_manager = TTSConfigManager(config_dir=tmpdir)
        config = tts_manager.get_config()
        assert config.model == "from-app-config"


def test_tts_config_save_to_app_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        from packages.provider_config.config_reader import ConfigReader

        tts_manager = TTSConfigManager(config_dir=tmpdir)
        tts_manager.save_config(TTSConfig(model="saved-model"))

        reader = ConfigReader(config_dir=tmpdir)
        assert reader.get_tts_config()["model"] == "saved-model"


# ---------------------------------------------------------------------------
# Anti-drift invariant: TTSConfigManager and ConfigReader resolve to same values
# ---------------------------------------------------------------------------


def test_defaults_consistent_between_reader_and_manager() -> None:
    """TTSConfigManager.get_config() 与 ConfigReader.get_tts_config() 解析出的 model/voice 一致"""
    from packages.provider_config.config_io import save_config
    from packages.provider_config.config_reader import ConfigReader

    # Scenario 1: no config files at all — both fall back to factory defaults
    with tempfile.TemporaryDirectory() as tmpdir:
        reader = ConfigReader(config_dir=tmpdir)
        manager = TTSConfigManager(config_dir=tmpdir)

        reader_config = reader.get_tts_config()
        manager_config = manager.get_config()

        assert manager_config.model == reader_config["model"], (
            f"model mismatch: TTSConfigManager={manager_config.model} "
            f"vs ConfigReader={reader_config['model']}"
        )
        assert manager_config.voice == reader_config["voice"], (
            f"voice mismatch: TTSConfigManager={manager_config.voice} "
            f"vs ConfigReader={reader_config['voice']}"
        )

    # Scenario 2: empty app_config.json — both read DEFAULTS via ConfigReader
    with tempfile.TemporaryDirectory() as tmpdir:
        save_config(Path(tmpdir) / "app_config.json", {})
        reader = ConfigReader(config_dir=tmpdir)
        manager = TTSConfigManager(config_dir=tmpdir)

        reader_config = reader.get_tts_config()
        manager_config = manager.get_config()

        assert manager_config.model == reader_config["model"]
        assert manager_config.voice == reader_config["voice"]

    # Scenario 4: active product scope override
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "app_config.json"
        save_config(
            config_path,
            {
                "active_product_id": "prod-1",
                "products": [
                    {
                        "id": "prod-1",
                        "tts": {"voice": "ProductVoice"},
                    }
                ],
            },
        )
        reader = ConfigReader(config_dir=tmpdir)
        manager = TTSConfigManager(config_dir=tmpdir)

        reader_config = reader.get_tts_config(product_id="prod-1")
        manager_config = manager.get_config()

        assert manager_config.model == reader_config["model"]
        assert manager_config.voice == reader_config["voice"]


# ---------------------------------------------------------------------------
# Factory default validity
# ---------------------------------------------------------------------------


def test_factory_default_model_is_valid() -> None:
    """config_constants.DEFAULTS[\"tts\"][\"model\"] 是 MODEL_TO_PROVIDER 中存在的有效 model"""
    from apps.control_plane.routes.tts import MODEL_TO_PROVIDER
    from packages.provider_config.config_constants import DEFAULTS

    model = DEFAULTS["tts"]["model"]
    assert model in MODEL_TO_PROVIDER, (
        f"Default TTS model '{model}' is not recognised by MODEL_TO_PROVIDER. "
        f"Valid models: {list(MODEL_TO_PROVIDER)}"
    )
