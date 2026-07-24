from __future__ import annotations

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


def test_save_and_load_product_config() -> None:
    """product_id 配置可写回读：写入 app_config.json 的 products[i].tts"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from packages.provider_config.config_io import save_config

        # 预先创建 app_config.json 确保 ConfigReader 能找到
        config_path = Path(tmpdir) / "app_config.json"
        save_config(config_path, {"products": [{"id": "prod-1"}]})

        manager = TTSConfigManager(config_dir=tmpdir)
        manager.save_config(TTSConfig(model="product-model"), product_id="prod-1")

        loaded = manager.get_config(product_id="prod-1")
        assert loaded.model == "product-model"


def test_save_product_config_raises_for_missing_product() -> None:
    """save_config(product_id=不存在) 应抛出 ValueError。"""
    import pytest

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = TTSConfigManager(config_dir=tmpdir)
        with pytest.raises(ValueError, match="product 'nonexistent' not found"):
            manager.save_config(TTSConfig(model="test"), product_id="nonexistent")


# ---------------------------------------------------------------------------
# TTSConfigManager product config (via app_config.json)
# ---------------------------------------------------------------------------


def test_product_config_without_global() -> None:
    """只有 product 级 tts，顶层 tts 为空 → product 配置应返回自身，defaults 填充其余"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from packages.provider_config.config_io import save_config

        config_path = Path(tmpdir) / "app_config.json"
        save_config(
            config_path,
            {"products": [{"id": "prod-1", "tts": {"model": "product-only"}}]},
        )

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config(product_id="prod-1")
        assert config.model == "product-only"
        assert config.voice == "Cherry"  # default


def test_product_overrides_global() -> None:
    """product 级 tts 覆盖顶层 tts"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from packages.provider_config.config_io import save_config

        config_path = Path(tmpdir) / "app_config.json"
        save_config(
            config_path,
            {
                "tts": {"model": "global-model", "voice": "GlobalVoice"},
                "products": [{"id": "prod-1", "tts": {"model": "prod-model"}}],
            },
        )

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config(product_id="prod-1")
        assert config.model == "prod-model"  # product overrides
        assert config.voice == "GlobalVoice"  # from global


def test_nonexistent_product_uses_global() -> None:
    """不存在的 product_id → ConfigReader 返回顶层 tts"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from packages.provider_config.config_io import save_config

        config_path = Path(tmpdir) / "app_config.json"
        save_config(config_path, {"tts": {"model": "global-model"}})

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config(product_id="nonexistent")
        assert config.model == "global-model"


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

    # Scenario 4: product scope
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "app_config.json"
        save_config(
            config_path,
            {
                "products": [
                    {
                        "id": "prod-1",
                        "tts": {"voice": "ProductVoice"},
                    }
                ],
            },
        )
        # Manager.get_config(product_id="prod-1") 获取 product 级配置
        reader = ConfigReader(config_dir=tmpdir)
        manager = TTSConfigManager(config_dir=tmpdir)

        reader_config = reader.get_tts_config(product_id="prod-1")
        manager_config = manager.get_config(product_id="prod-1")

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


# ---------------------------------------------------------------------------
# DEFAULTS constant validity
# ---------------------------------------------------------------------------


def test_app_config_defaults_audio_format() -> None:
    """ConfigReader DEFAULTS 中 tts 音频格式应为 wav"""
    from packages.provider_config.config_constants import DEFAULTS

    assert DEFAULTS["tts"]["audio_format"] == "wav"


# ---------------------------------------------------------------------------
# optimize_text_preview 配置字段
# ---------------------------------------------------------------------------


def test_tts_config_has_optimize_text_preview() -> None:
    config = TTSConfig()
    assert hasattr(config, "optimize_text_preview")


def test_optimize_text_preview_default_false() -> None:
    config = TTSConfig()
    assert config.optimize_text_preview is False


def test_optimize_text_preview_to_dict() -> None:
    config = TTSConfig(optimize_text_preview=True)
    config_dict = config.to_dict()
    assert config_dict["optimize_text_preview"] is True


def test_optimize_text_preview_from_dict() -> None:
    data = {"optimize_text_preview": True}
    config = TTSConfig.from_dict(data)
    assert config.optimize_text_preview is True


# ---------------------------------------------------------------------------
# voiceclone 配置字段
# ---------------------------------------------------------------------------


def test_tts_config_has_voiceclone_fields() -> None:
    config = TTSConfig()
    assert hasattr(config, "voice_clone_sample_path")
    assert hasattr(config, "voice_clone_mime_type")


def test_tts_config_voiceclone_defaults() -> None:
    config = TTSConfig()
    assert config.voice_clone_sample_path is None
    assert config.voice_clone_mime_type is None


def test_tts_config_voiceclone_to_dict() -> None:
    config = TTSConfig(
        voice_clone_sample_path="voice_clone_sample.mp3",
        voice_clone_mime_type="audio/mpeg",
    )
    config_dict = config.to_dict()
    assert config_dict["voice_clone_sample_path"] == "voice_clone_sample.mp3"
    assert config_dict["voice_clone_mime_type"] == "audio/mpeg"


def test_tts_config_voiceclone_from_dict() -> None:
    data = {
        "voice_clone_sample_path": "voice_clone_sample.mp3",
        "voice_clone_mime_type": "audio/wav",
    }
    config = TTSConfig.from_dict(data)
    assert config.voice_clone_sample_path == "voice_clone_sample.mp3"
    assert config.voice_clone_mime_type == "audio/wav"
