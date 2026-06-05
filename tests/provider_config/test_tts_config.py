from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packages.provider_config.tts_config import TTSConfig, TTSConfigManager


# ---------------------------------------------------------------------------
# TTSConfig defaults via with_defaults()
# ---------------------------------------------------------------------------


def test_default_model() -> None:
    assert TTSConfig().with_defaults().model == "mimo-v2.5-tts"


def test_default_voice() -> None:
    assert TTSConfig().with_defaults().voice == "Mia"


def test_default_fallback_voice() -> None:
    assert TTSConfig().with_defaults().fallback_voice == "Dean"


def test_default_randomize_voice() -> None:
    assert TTSConfig().with_defaults().randomize_voice is True


def test_default_random_voices() -> None:
    assert TTSConfig().with_defaults().random_voices == ["Mia", "Dean"]


def test_default_voice_design_prompt() -> None:
    assert TTSConfig().with_defaults().voice_design_prompt == ""


def test_default_style_prompt() -> None:
    assert TTSConfig().with_defaults().style_prompt == "自然 清晰 适合短视频带货口播"


def test_default_audio_format() -> None:
    assert TTSConfig().with_defaults().audio_format == "mp3"


def test_default_sample_rate() -> None:
    assert TTSConfig().with_defaults().sample_rate is None


def test_default_bitrate() -> None:
    assert TTSConfig().with_defaults().bitrate is None


def test_default_channel() -> None:
    assert TTSConfig().with_defaults().channel is None


def test_default_enable_request_logging() -> None:
    assert TTSConfig().with_defaults().enable_request_logging is False


def test_default_enable_performance_metrics() -> None:
    assert TTSConfig().with_defaults().enable_performance_metrics is True


def test_default_log_audio_duration() -> None:
    assert TTSConfig().with_defaults().log_audio_duration is True


# ---------------------------------------------------------------------------
# TTSConfig custom values
# ---------------------------------------------------------------------------


def test_custom_model() -> None:
    assert TTSConfig(model="custom-model").model == "custom-model"


def test_custom_voice() -> None:
    assert TTSConfig(voice="CustomVoice").voice == "CustomVoice"


def test_custom_random_voices() -> None:
    assert TTSConfig(random_voices=["A", "B", "C"]).random_voices == ["A", "B", "C"]


def test_custom_sample_rate() -> None:
    assert TTSConfig(sample_rate=44100).sample_rate == 44100


def test_custom_bitrate() -> None:
    assert TTSConfig(bitrate=128000).bitrate == 128000


def test_custom_channel() -> None:
    assert TTSConfig(channel=2).channel == 2


# ---------------------------------------------------------------------------
# TTSConfig.to_dict
# ---------------------------------------------------------------------------


def test_to_dict_returns_all_fields() -> None:
    config = TTSConfig()
    data = config.to_dict()
    assert len(data) == 14


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
    original = TTSConfig(model="test", voice="voice", sample_rate=44100)
    restored = TTSConfig.from_dict(original.to_dict())
    assert restored.model == original.model
    assert restored.voice == original.voice
    assert restored.sample_rate == original.sample_rate


def test_from_dict_ignores_unknown_keys() -> None:
    data = {"model": "test", "unknown_key": "value"}
    config = TTSConfig.from_dict(data)
    assert config.model == "test"
    assert not hasattr(config, "unknown_key")


# ---------------------------------------------------------------------------
# TTSConfig.with_defaults
# ---------------------------------------------------------------------------


def test_with_defaults_fills_none() -> None:
    config = TTSConfig(model="custom")
    with_defaults = config.with_defaults()
    assert with_defaults.model == "custom"
    assert with_defaults.voice == "Mia"


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
        assert config.model == "mimo-v2.5-tts"
        assert config.voice == "Mia"


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
        (projects_dir / "tts_config.json").write_text(json.dumps({"model": "project-only"}))

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config(project_id="proj-1")
        assert config.model == "project-only"
        assert config.voice == "Mia"  # default


def test_project_overrides_global() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        global_path = Path(tmpdir) / "tts_config.json"
        global_path.write_text(json.dumps({"model": "global-model", "voice": "GlobalVoice"}))

        projects_dir = Path(tmpdir) / "projects" / "proj-1"
        projects_dir.mkdir(parents=True)
        (projects_dir / "tts_config.json").write_text(json.dumps({"model": "project-model"}))

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
    base = TTSConfig(sample_rate=44100)
    override = TTSConfig(sample_rate=None)
    merged = TTSConfigManager._merge_configs(base, override)
    assert merged.sample_rate == 44100  # None does not override


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
    base = TTSConfig(voice_design_prompt="", sample_rate=None)
    override = TTSConfig(voice_design_prompt="new prompt", sample_rate=48000)
    merged = TTSConfigManager._merge_configs(base, override)
    assert merged.voice_design_prompt == "new prompt"
    assert merged.sample_rate == 48000


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
