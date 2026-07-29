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
    assert len(data) == 31


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
    """默认 TTS model 应由 catalog 映射到默认 provider。"""
    from packages.provider_config.catalog import tts_provider_for_model
    from packages.provider_config.config_constants import DEFAULTS

    model = DEFAULTS["tts"]["model"]
    assert tts_provider_for_model(model) == DEFAULTS["tts"]["provider"]


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


# ---------------------------------------------------------------------------
# New provider connection fields (#386)
# ---------------------------------------------------------------------------


def test_new_provider_fields_default_to_none() -> None:
    """新建 TTSConfig() 后 10 个新 provider 连接字段均为 None"""
    config = TTSConfig()
    assert config.speed is None
    assert config.vol is None
    assert config.pitch is None
    assert config.emotion is None
    assert config.sample_rate is None
    assert config.bitrate is None
    assert config.channel is None
    assert config.group_id is None
    assert config.endpoint is None
    assert config.extra_headers is None


def test_new_provider_fields_roundtrip_to_dict() -> None:
    """to_dict/from_dict 保留新 provider 连接字段值"""
    config = TTSConfig(
        speed="1.0",
        vol="0.8",
        pitch="0.0",
        emotion="happy",
        sample_rate="24000",
        bitrate="128",
        channel="1",
        group_id="group-123",
        endpoint="https://custom.example.com/v1",
        extra_headers='{"X-Custom": "value"}',
    )
    data = config.to_dict()
    assert data["speed"] == "1.0"
    assert data["vol"] == "0.8"
    assert data["pitch"] == "0.0"
    assert data["emotion"] == "happy"
    assert data["sample_rate"] == "24000"
    assert data["bitrate"] == "128"
    assert data["channel"] == "1"
    assert data["group_id"] == "group-123"
    assert data["endpoint"] == "https://custom.example.com/v1"
    assert data["extra_headers"] == '{"X-Custom": "value"}'

    restored = TTSConfig.from_dict(data)
    assert restored.speed == "1.0"
    assert restored.vol == "0.8"
    assert restored.pitch == "0.0"
    assert restored.emotion == "happy"


def test_from_dict_coerces_numeric_string_fields() -> None:
    """数值形式的连接参数（如 sample_rate: 44100）规范化为字符串"""
    config = TTSConfig.from_dict(
        {"sample_rate": 44100, "bitrate": 192000, "channel": 2}
    )
    assert config.sample_rate == "44100"
    assert config.bitrate == "192000"
    assert config.channel == "2"


def test_from_dict_ignores_removed_voice_id() -> None:
    """已移除的 voice_id 字段被静默忽略"""
    config = TTSConfig.from_dict({"voice_id": "voice-456"})
    assert not hasattr(config, "voice_id")


def test_with_defaults_fills_provider_params() -> None:
    """with_defaults() 从 DEFAULTS 填充 provider 连接参数（新字段默认 None，不应有默认值）"""
    config = TTSConfig().with_defaults()
    # 新字段在 DEFAULTS 中无对应值时保持 None
    assert config.speed is None
    assert config.vol is None
    assert config.pitch is None
    assert config.emotion is None


def test_to_dict_field_count_updated() -> None:
    """field count 反映新增的 10 个 provider 连接字段（21 → 31）"""
    config = TTSConfig()
    data = config.to_dict()
    assert len(data) == 31


def test_save_and_load_preserves_provider_params() -> None:
    """TTSConfigManager roundtrip 保留新 provider 连接字段"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = TTSConfigManager(config_dir=tmpdir)
        config = TTSConfig(
            model="mimo-v2.5-tts",
            voice="Mia",
            speed="1.2",
            vol="0.9",
            pitch="-0.1",
            emotion="calm",
            group_id="my-group",
            endpoint="https://custom.example.com/v1",
            extra_headers='{"X-Custom": "v"}',
        )
        manager.save_config(config)
        loaded = manager.get_config()
        assert loaded.speed == "1.2"
        assert loaded.vol == "0.9"
        assert loaded.pitch == "-0.1"
        assert loaded.emotion == "calm"
        assert loaded.group_id == "my-group"
        assert loaded.endpoint == "https://custom.example.com/v1"
        assert loaded.extra_headers == '{"X-Custom": "v"}'


def test_save_and_load_product_provider_params() -> None:
    """product 级 provider 连接参数持久化与回读"""
    with tempfile.TemporaryDirectory() as tmpdir:
        from packages.provider_config.config_io import save_config

        config_path = Path(tmpdir) / "app_config.json"
        save_config(config_path, {"products": [{"id": "prod-1"}]})

        manager = TTSConfigManager(config_dir=tmpdir)
        config = TTSConfig(
            model="mimo-v2.5-tts",
            speed="0.8",
            vol="0.7",
            group_id="product-group",
        )
        manager.save_config(config, product_id="prod-1")
        loaded = manager.get_config(product_id="prod-1")
        assert loaded.speed == "0.8"
        assert loaded.vol == "0.7"
        assert loaded.group_id == "product-group"


def test_from_dict_ignores_dead_provider_profile_fields() -> None:
    """旧 provider_profiles 残余字段在 from_dict 中被静默忽略"""
    config = TTSConfig.from_dict(
        {
            "model": "test",
            "sample_rate": "48000",  # old profile field, now a first-class field
            "some_dead_field": "should_be_ignored",
        }
    )
    assert config.model == "test"
    assert config.sample_rate == "48000"  # valid new field
    assert not hasattr(config, "some_dead_field")


# ---------------------------------------------------------------------------
# resolve_tts_config — single runtime entry point (#386)
# ---------------------------------------------------------------------------


def test_resolve_tts_config_infers_provider_from_model() -> None:
    from packages.provider_config.tts_config import resolve_tts_config

    config = resolve_tts_config({"model": "mimo-v2.5-tts"})
    assert config.provider == "mimo"
    assert config.model == "mimo-v2.5-tts"


def test_resolve_tts_config_applies_overrides() -> None:
    from packages.provider_config.tts_config import resolve_tts_config

    config = resolve_tts_config(
        {"provider": "qwen", "model": "qwen3-tts-flash", "voice": "Cherry"},
        {"model": "mimo-v2.5-tts", "voice": "Mia"},
    )
    assert config.model == "mimo-v2.5-tts"
    assert config.voice == "Mia"
    # A model override without an explicit provider override re-infers the
    # provider from the new model so the runtime routes to the right backend.
    assert config.provider == "mimo"


def test_resolve_tts_config_explicit_provider_override_wins() -> None:
    from packages.provider_config.tts_config import resolve_tts_config

    config = resolve_tts_config(
        {"provider": "qwen", "model": "qwen3-tts-flash", "voice": "Cherry"},
        {"model": "mimo-v2.5-tts", "voice": "Mia", "provider": "qwen"},
    )
    assert config.model == "mimo-v2.5-tts"
    assert config.voice == "Mia"
    assert config.provider == "qwen"


def test_resolve_tts_config_override_model_reinfers_provider() -> None:
    from packages.provider_config.tts_config import resolve_tts_config

    # Base dict has no provider; override model drives inference.
    config = resolve_tts_config({}, {"model": "mimo-v2.5-tts"})
    assert config.provider == "mimo"


def test_resolve_tts_config_flattens_nested_keys() -> None:
    from packages.provider_config.tts_config import resolve_tts_config

    config = resolve_tts_config(
        {
            "model": "qwen3-tts-flash",
            "director": {
                "character": "女主播",
                "scene": "直播间",
                "guidance": "语速适中",
            },
            "audio_tags": {"enabled": True, "tags": "(温柔)"},
        }
    )
    assert config.director_character == "女主播"
    assert config.audio_tags_enabled is True
    assert config.audio_tags == "(温柔)"
