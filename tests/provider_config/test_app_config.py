from __future__ import annotations

import tempfile

from packages.provider_config.app_config import AppConfigManager


def test_get_tts_model_default() -> None:
    """AppConfigManager 应返回默认 TTS 模型"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_tts_config()
        assert config["model"] == "qwen-tts"


def test_get_tts_voice_default() -> None:
    """AppConfigManager 应返回默认 TTS 音色"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_tts_config()
        assert config["voice"] == "Cherry"


def test_set_tts_model() -> None:
    """AppConfigManager 应能保存 TTS 模型"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_tts("model", "custom-model")
        config = manager.get_tts_config()
        assert config["model"] == "custom-model"


def test_set_tts_voice() -> None:
    """AppConfigManager 应能保存 TTS 音色"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_tts("voice", "CustomVoice")
        config = manager.get_tts_config()
        assert config["voice"] == "CustomVoice"


def test_persistence() -> None:
    """AppConfigManager 应能持久化配置到文件"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager1 = AppConfigManager(config_dir=tmpdir)
        manager1.set_tts("model", "persisted-model")

        manager2 = AppConfigManager(config_dir=tmpdir)
        config = manager2.get_tts_config()
        assert config["model"] == "persisted-model"


def test_get_nested_tts_config() -> None:
    """AppConfigManager 应能获取嵌套的 TTS 配置"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_tts_config()
        assert "director" in config
        assert "character" in config["director"]


def test_set_tts_nested_key() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_tts("director.character", "测试角色")
        assert manager.get_tts_value("director.character") == "测试角色"


def test_set_tts_nested_key_preserves_sibling() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_tts("director.character", "测试角色")
        manager.set_tts("director.scene", "测试场景")
        assert manager.get_tts_value("director.character") == "测试角色"
        assert manager.get_tts_value("director.scene") == "测试场景"


def test_get_tts_value_nested_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_tts_value("director.character") == ""


def test_get_tts_value_nested_missing_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_tts_value("nonexistent.key", "fallback") == "fallback"


def test_get_tts_config_deep_merge_preserves_nested_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_tts("director.character", "自定义角色")
        config = manager.get_tts_config()
        assert config["director"]["character"] == "自定义角色"
        assert config["director"]["scene"] == ""
        assert config["director"]["guidance"] == ""


def test_set_tts_flat_key_still_works() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_tts("model", "custom-model")
        assert manager.get_tts_value("model") == "custom-model"


def test_set_tts_audio_tags_nested() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_tts("audio_tags.enabled", True)
        manager.set_tts("audio_tags.tags", "(温柔)[笑声]")
        assert manager.get_tts_value("audio_tags.enabled") is True
        assert manager.get_tts_value("audio_tags.tags") == "(温柔)[笑声]"


def test_get_api_key_from_env(monkeypatch) -> None:
    """API Key 应从环境变量读取"""
    monkeypatch.setattr("packages.provider_config.app_config.load_dotenv", None)
    monkeypatch.setenv("MIMO_API_KEY", "test-key-123")
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_api_key("mimo") == "test-key-123"


def test_get_api_key_missing(monkeypatch) -> None:
    """API Key 不存在时应返回空字符串"""
    monkeypatch.setattr("packages.provider_config.app_config.load_dotenv", None)
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_api_key("mimo") == ""


def test_get_api_base_url_from_env(monkeypatch) -> None:
    """API Base URL 应从环境变量读取"""
    monkeypatch.setenv("MIMO_API_BASE_URL", "https://custom.api.com/v1")
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_api_base_url("mimo") == "https://custom.api.com/v1"


def test_get_video_config_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_video_config()
        assert config["cover_title_style"]["primary_color"] == "#FFD700"
        assert config["cover_title_style"]["outline_width"] == 2.0
        assert config["cover_title_style"]["position"] == "center"


def test_set_video_cover_title_style() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_video("cover_title_style.primary_color", "#FFFFFF")
        assert manager.get_video_value("cover_title_style.primary_color") == "#FFFFFF"


def test_get_video_config_deep_merge_preserves_defaults() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_video("cover_title_style.position", "top")
        config = manager.get_video_config()
        assert config["cover_title_style"]["position"] == "top"
        assert config["cover_title_style"]["primary_color"] == "#FFD700"


# --- Vision tests ---


def test_get_vision_config_default() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_vision_config()
        assert config["provider"] == "xiaomi"
        assert config["model"] == "mimo-v2.5"


def test_get_vision_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("XIAOMI_VISION_API_KEY", "test-vision-key")
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_vision_api_key() == "test-vision-key"


def test_get_vision_endpoint_from_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "XIAOMI_VISION_API_URL", "https://api.example.com/v1/chat/completions"
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert (
            manager.get_vision_endpoint()
            == "https://api.example.com/v1/chat/completions"
        )


def test_get_vision_model_from_env(monkeypatch) -> None:
    monkeypatch.setenv("XIAOMI_VISION_MODEL", "mimo-v2-omni")
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_vision_model() == "mimo-v2-omni"


def test_set_vision_model() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.set_vision("model", "mimo-v2-omni")
        config = manager.get_vision_config()
        assert config["model"] == "mimo-v2-omni"


def test_vision_api_key_empty_when_not_set(monkeypatch) -> None:
    monkeypatch.setattr("packages.provider_config.app_config.load_dotenv", None)
    monkeypatch.delenv("XIAOMI_VISION_API_KEY", raising=False)
    monkeypatch.delenv("VISION_API_KEY", raising=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_vision_api_key() == ""


# --- LLM api_key/endpoint tests ---


def test_get_llm_api_key_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-deepseek")
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_llm_api_key() == "sk-test-deepseek"


def test_get_llm_endpoint_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_llm_endpoint() == "https://api.deepseek.com/chat/completions"


def test_get_llm_api_key_empty_when_not_set(monkeypatch) -> None:
    monkeypatch.setattr("packages.provider_config.app_config.load_dotenv", None)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        assert manager.get_llm_api_key() == ""


# --- Scene config tests (#59) ---


def test_get_scene_config_default() -> None:
    """无 scene 配置时返回 DEFAULTS。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        config = manager.get_scene_config()
        assert config["folders"] == []
        assert config["transition_duration_ms"] == 500


def test_get_scene_config_from_product_level() -> None:
    """产品级 scene 配置优先于顶级 scene 配置。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        manager.save_product_config("prod_001", {
            "scene": {
                "folders": [
                    {"name": "品牌开场", "path": "scene/brand-intro"},
                    {"name": "产品展示", "path": "scene/product-show"},
                ],
                "transition_duration_ms": 800,
            }
        })
        config = manager.get_scene_config()
        assert len(config["folders"]) == 2
        assert config["folders"][0]["name"] == "品牌开场"
        assert config["folders"][0]["path"] == "scene/brand-intro"
        assert config["folders"][1]["name"] == "产品展示"
        assert config["folders"][1]["path"] == "scene/product-show"
        assert config["transition_duration_ms"] == 800


def test_get_scene_config_product_overrides_top_level() -> None:
    """产品级 scene 配置应覆盖顶级 scene 配置。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        # 写入顶级 scene（模拟旧格式）
        raw = manager._load()
        raw["scene"] = {
            "folders": [{"name": "旧文件夹", "path": "scene/old"}],
            "transition_duration_ms": 300,
        }
        manager._save(raw)

        # 写入产品级 scene（模拟新产品格式）
        manager.switch_product("prod_001")
        manager.save_product_config("prod_001", {
            "scene": {
                "folders": [{"name": "新文件夹", "path": "scene/new"}],
                "transition_duration_ms": 600,
            }
        })

        config = manager.get_scene_config()
        # 产品级优先
        assert len(config["folders"]) == 1
        assert config["folders"][0]["name"] == "新文件夹"
        assert config["transition_duration_ms"] == 600


def test_get_scene_config_falls_back_to_top_level() -> None:
    """产品级无 scene 配置时回退到顶级 scene 配置。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        # 写入顶级 scene
        raw = manager._load()
        raw["scene"] = {
            "folders": [{"name": "回退文件夹", "path": "scene/fallback"}],
            "transition_duration_ms": 400,
        }
        manager._save(raw)

        # 创建产品但不设置 scene
        manager.switch_product("prod_001")

        config = manager.get_scene_config()
        assert len(config["folders"]) == 1
        assert config["folders"][0]["name"] == "回退文件夹"
        assert config["transition_duration_ms"] == 400


def test_get_scene_config_product_scene_partial_merge() -> None:
    """产品级 scene 仅部分字段时，其余字段回退到 DEFAULTS。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = AppConfigManager(config_dir=tmpdir)
        manager.switch_product("prod_001")
        manager.save_product_config("prod_001", {
            "scene": {
                "folders": [{"name": "单文件夹", "path": "scene/only"}],
                # transition_duration_ms 未设置
            }
        })
        config = manager.get_scene_config()
        assert len(config["folders"]) == 1
        assert config["folders"][0]["name"] == "单文件夹"
        # 未设置的字段从 DEFAULTS 合并
        assert config["transition_duration_ms"] == 500
