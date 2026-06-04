from __future__ import annotations

import json
import tempfile
from pathlib import Path

from packages.provider_config.tts_config import TTSConfig, TTSConfigManager


# ---------------------------------------------------------------------------
# TTSConfig defaults
# ---------------------------------------------------------------------------


def test_default_model() -> None:
    assert TTSConfig().model == "mimo-v2.5-tts"


def test_default_voice() -> None:
    assert TTSConfig().voice == "Mia"


def test_default_fallback_voice() -> None:
    assert TTSConfig().fallback_voice == "Dean"


def test_default_randomize_voice() -> None:
    assert TTSConfig().randomize_voice is True


def test_default_random_voices() -> None:
    assert TTSConfig().random_voices == ["Mia", "Dean"]


def test_default_voice_design_prompt() -> None:
    assert TTSConfig().voice_design_prompt == ""


def test_default_style_prompt() -> None:
    assert TTSConfig().style_prompt == "自然 清晰 适合短视频带货口播"


def test_default_audio_format() -> None:
    assert TTSConfig().audio_format == "mp3"


def test_default_sample_rate() -> None:
    assert TTSConfig().sample_rate is None


def test_default_bitrate() -> None:
    assert TTSConfig().bitrate is None


def test_default_channel() -> None:
    assert TTSConfig().channel is None


def test_default_enable_request_logging() -> None:
    assert TTSConfig().enable_request_logging is False


def test_default_enable_performance_metrics() -> None:
    assert TTSConfig().enable_performance_metrics is True


def test_default_log_audio_duration() -> None:
    assert TTSConfig().log_audio_duration is True


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
# TTSConfig serialization
# ---------------------------------------------------------------------------


def test_to_dict_returns_all_fields() -> None:
    data = TTSConfig().to_dict()
    expected_keys = {
        "model", "voice", "fallback_voice", "randomize_voice",
        "random_voices", "voice_design_prompt", "style_prompt",
        "audio_format", "sample_rate", "bitrate", "channel",
        "enable_request_logging", "enable_performance_metrics",
        "log_audio_duration",
    }
    assert set(data.keys()) == expected_keys


def test_to_dict_values_match_defaults() -> None:
    data = TTSConfig().to_dict()
    assert data["model"] == "mimo-v2.5-tts"
    assert data["voice"] == "Mia"
    assert data["fallback_voice"] == "Dean"
    assert data["randomize_voice"] is True
    assert data["random_voices"] == ["Mia", "Dean"]
    assert data["audio_format"] == "mp3"
    assert data["sample_rate"] is None


def test_to_dict_custom_values() -> None:
    data = TTSConfig(model="test-model", sample_rate=48000).to_dict()
    assert data["model"] == "test-model"
    assert data["sample_rate"] == 48000


def test_from_dict_creates_config() -> None:
    data = {
        "model": "test-model",
        "voice": "TestVoice",
        "fallback_voice": "BackupVoice",
        "randomize_voice": False,
        "random_voices": ["X", "Y"],
        "voice_design_prompt": "test prompt",
        "style_prompt": "test style",
        "audio_format": "wav",
        "sample_rate": 22050,
        "bitrate": 64000,
        "channel": 1,
        "enable_request_logging": True,
        "enable_performance_metrics": False,
        "log_audio_duration": False,
    }
    config = TTSConfig.from_dict(data)
    assert config.model == "test-model"
    assert config.voice == "TestVoice"
    assert config.fallback_voice == "BackupVoice"
    assert config.randomize_voice is False
    assert config.random_voices == ["X", "Y"]
    assert config.voice_design_prompt == "test prompt"
    assert config.style_prompt == "test style"
    assert config.audio_format == "wav"
    assert config.sample_rate == 22050
    assert config.bitrate == 64000
    assert config.channel == 1
    assert config.enable_request_logging is True
    assert config.enable_performance_metrics is False
    assert config.log_audio_duration is False


def test_from_dict_partial_data_uses_defaults() -> None:
    config = TTSConfig.from_dict({"model": "partial-model"})
    assert config.model == "partial-model"
    assert config.voice == "Mia"  # default
    assert config.audio_format == "mp3"  # default


def test_from_dict_empty_dict_uses_defaults() -> None:
    config = TTSConfig.from_dict({})
    assert config.model == "mimo-v2.5-tts"
    assert config.voice == "Mia"


def test_roundtrip_to_dict_from_dict() -> None:
    original = TTSConfig(
        model="roundtrip-model",
        voice="RTVoice",
        sample_rate=44100,
        random_voices=["A", "B"],
    )
    restored = TTSConfig.from_dict(original.to_dict())
    assert restored.model == original.model
    assert restored.voice == original.voice
    assert restored.sample_rate == original.sample_rate
    assert restored.random_voices == original.random_voices


def test_from_dict_ignores_unknown_keys() -> None:
    config = TTSConfig.from_dict({"model": "test", "unknown_key": "value"})
    assert config.model == "test"
    assert not hasattr(config, "unknown_key")


# ---------------------------------------------------------------------------
# TTSConfigManager.get_config
# ---------------------------------------------------------------------------


def test_get_config_returns_default_when_no_files() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config()
        assert config.model == "mimo-v2.5-tts"
        assert config.voice == "Mia"


def test_get_config_loads_global_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "tts_config.json"
        config_path.write_text(json.dumps({"model": "global-model", "voice": "GlobalVoice"}))

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config()
        assert config.model == "global-model"
        assert config.voice == "GlobalVoice"


def test_get_config_project_overrides_global() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        global_path = Path(tmpdir) / "tts_config.json"
        global_path.write_text(json.dumps({"model": "global-model", "voice": "GlobalVoice"}))

        projects_dir = Path(tmpdir) / "projects"
        projects_dir.mkdir()
        project_path = projects_dir / "proj-1" / "tts_config.json"
        project_path.parent.mkdir(parents=True)
        project_path.write_text(json.dumps({"model": "project-model"}))

        manager = TTSConfigManager(config_dir=tmpdir)
        config = manager.get_config(project_id="proj-1")
        assert config.model == "project-model"  # project overrides
        assert config.voice == "GlobalVoice"  # inherits global


# ---------------------------------------------------------------------------
# TTSConfigManager save/load
# ---------------------------------------------------------------------------


def test_save_and_load_global_config() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = TTSConfigManager(config_dir=tmpdir)
        original = TTSConfig(model="saved-model", voice="SavedVoice")
        manager.save_config(original)

        loaded = manager.get_config()
        assert loaded.model == "saved-model"
        assert loaded.voice == "SavedVoice"


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
