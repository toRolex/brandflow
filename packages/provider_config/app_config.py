from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.pipeline_services.asset_library.category_config import (
    CategoryConfig,
    default_categories,
)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv: Any | None = None


DEFAULTS: dict[str, Any] = {
    "llm": {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "thinking": "disabled",
    },
    "tts": {
        "provider": "mimo",
        "model": "mimo-v2.5-tts",
        "voice": "Mia",
        "fallback_voice": "Dean",
        "randomize_voice": True,
        "random_voices": ["Mia", "Dean"],
        "style_prompt": "自然 清晰 适合短视频带货口播",
        "voice_design_prompt": "",
        "style_control_mode": "simple",
        "director": {
            "character": "",
            "scene": "",
            "guidance": "",
        },
        "audio_tags": {
            "enabled": False,
            "tags": "",
        },
        "audio_format": "wav",
        "sample_rate": None,
        "bitrate": None,
        "channel": None,
        "enable_request_logging": False,
        "enable_performance_metrics": True,
        "log_audio_duration": True,
    },
    "vision": {
        "provider": "xiaomi",
        "model": "mimo-v2.5",
    },
    "media": {
        "ffmpeg_path": "ffmpeg",
        "ffprobe_path": "ffprobe",
        "subtitle_mode": "script_timed",
        "max_retry": 3,
        "retry_delay_seconds": 60,
    },
    "asset_library": {
        "categories": [],
        "category_suggestion_model": "deepseek-v4-flash",
        "category_suggestion_sample_size": 20,
    },
    "video": {
        "cover_title_style": {
            "primary_color": "#FFD700",
            "outline_color": "#000000",
            "highlight_color": "#FF0000",
            "outline_width": 2.0,
            "position": "center",
        }
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """深度合并两个字典，override 中的值覆盖 base 中的值，嵌套字典递归合并。"""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _get_nested(data: dict[str, Any], key_path: str, default: Any = None) -> Any:
    """通过点分路径获取嵌套字典的值，如 'director.character'。"""
    keys = key_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _set_nested(data: dict[str, Any], key_path: str, value: Any) -> None:
    """通过点分路径设置嵌套字典的值，如 'director.character'。"""
    keys = key_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


class AppConfigManager:
    """统一配置管理器，读写 config/app_config.json"""

    API_KEY_ENV_MAP = {
        "mimo": "MIMO_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
        "minimax": "MINIMAX_API_KEY",
    }

    API_BASE_URL_ENV_MAP = {
        "mimo": "MIMO_API_BASE_URL",
        "qwen": "DASHSCOPE_API_URL",
        "deepseek": "DEEPSEEK_API_URL",
        "kimi": "KIMI_API_URL",
        "minimax": "MINIMAX_TTS_URL",
    }

    VISION_API_KEY_ENV_MAP = {
        "xiaomi": "XIAOMI_VISION_API_KEY",
        "openai": "VISION_API_KEY",
        "claude": "VISION_API_KEY",
    }

    VISION_ENDPOINT_ENV_MAP = {
        "xiaomi": "XIAOMI_VISION_API_URL",
        "openai": "VISION_API_URL",
        "claude": "VISION_API_URL",
    }

    VISION_MODEL_ENV_MAP = {
        "xiaomi": "XIAOMI_VISION_MODEL",
        "openai": "VISION_MODEL",
        "claude": "VISION_MODEL",
    }

    def __init__(self, config_dir: str | Path = "config") -> None:
        if load_dotenv is not None:
            env_path = Path.cwd() / ".env"
            if env_path.exists():
                load_dotenv(env_path, override=False)
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "app_config.json"

    def _load(self) -> dict[str, Any]:
        if self.config_path.exists():
            with open(self.config_path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save(self, config: dict[str, Any]) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    def get_tts_config(self) -> dict[str, Any]:
        config = self._load()
        tts = config.get("tts", {})
        defaults = DEFAULTS["tts"]
        return _deep_merge(defaults, tts)

    def set_tts(self, key: str, value: Any) -> None:
        config = self._load()
        if "tts" not in config:
            config["tts"] = {}
        _set_nested(config["tts"], key, value)
        self._save(config)

    def get_tts_value(self, key: str, default: Any = None) -> Any:
        config = self.get_tts_config()
        return _get_nested(config, key, default)

    def get_llm_config(self) -> dict[str, Any]:
        config = self._load()
        llm = config.get("llm", {})
        defaults = DEFAULTS["llm"]
        return _deep_merge(defaults, llm)

    def get_api_key(self, provider: str) -> str:
        import os

        # 优先读取 provider 专用 key，回退到通用 TTS_API_KEY 或 LLM_API_KEY
        env_key = self.API_KEY_ENV_MAP.get(provider, "")
        value = os.getenv(env_key, "").strip().strip('"').strip("'")
        if not value:
            # 根据 provider 类型回退到通用 key
            if provider in ("mimo", "minimax", "qwen"):
                value = os.getenv("TTS_API_KEY", "").strip().strip('"').strip("'")
            else:
                value = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")
        return value

    def get_api_base_url(self, provider: str) -> str:
        import os

        # 优先读取 provider 专用 endpoint，回退到通用 TTS_API_URL 或 LLM_API_URL
        env_key = self.API_BASE_URL_ENV_MAP.get(provider, "")
        value = os.getenv(env_key, "").strip().rstrip("/")
        if not value:
            if provider in ("mimo", "minimax"):
                value = os.getenv("TTS_API_URL", "").strip().rstrip("/")
            elif provider != "qwen":
                value = os.getenv("LLM_API_URL", "").strip().rstrip("/")
        return value

    def get_llm_api_key(self) -> str:
        import os

        provider = self.get_llm_config().get("provider", "deepseek")
        # 优先读取 provider 专用 key，回退到通用 LLM_API_KEY
        env_key = self.API_KEY_ENV_MAP.get(provider, "")
        value = os.getenv(env_key, "").strip().strip('"').strip("'")
        if not value:
            value = os.getenv("LLM_API_KEY", "").strip().strip('"').strip("'")
        return value

    def get_llm_endpoint(self) -> str:
        import os

        provider = self.get_llm_config().get("provider", "deepseek")
        # 优先读取 provider 专用 endpoint，回退到通用 LLM_API_URL
        env_key = self.API_BASE_URL_ENV_MAP.get(provider, "")
        value = os.getenv(env_key, "").strip().rstrip("/")
        if not value:
            value = os.getenv("LLM_API_URL", "").strip().rstrip("/")
        return value

    def get_vision_config(self) -> dict[str, Any]:
        config = self._load()
        vision = config.get("vision", {})
        defaults = DEFAULTS["vision"]
        return _deep_merge(defaults, vision)

    def set_vision(self, key: str, value: Any) -> None:
        config = self._load()
        if "vision" not in config:
            config["vision"] = {}
        _set_nested(config["vision"], key, value)
        self._save(config)

    def get_vision_api_key(self) -> str:
        import os

        provider = self.get_vision_config().get("provider", "xiaomi")
        # 优先读取 provider 专用 key，回退到通用 VISION_API_KEY
        env_key = self.VISION_API_KEY_ENV_MAP.get(provider, "VISION_API_KEY")
        value = os.getenv(env_key, "").strip().strip('"').strip("'")
        if not value:
            value = os.getenv("VISION_API_KEY", "").strip().strip('"').strip("'")
        return value

    def get_vision_endpoint(self) -> str:
        import os

        provider = self.get_vision_config().get("provider", "xiaomi")
        # 优先读取 provider 专用 endpoint，回退到通用 VISION_API_URL
        env_key = self.VISION_ENDPOINT_ENV_MAP.get(provider, "VISION_API_URL")
        value = os.getenv(env_key, "").strip().rstrip("/")
        if not value:
            value = os.getenv("VISION_API_URL", "").strip().rstrip("/")
        return value

    def get_vision_model(self) -> str:
        import os

        provider = self.get_vision_config().get("provider", "xiaomi")
        # 优先读取 provider 专用 model，回退到通用 VISION_MODEL
        env_key = self.VISION_MODEL_ENV_MAP.get(provider, "VISION_MODEL")
        value = os.getenv(env_key, "").strip()
        if not value:
            value = os.getenv("VISION_MODEL", "").strip()
        return value

    def get_media_config(self) -> dict[str, Any]:
        config = self._load()
        media = config.get("media", {})
        defaults = DEFAULTS["media"]
        return _deep_merge(defaults, media)

    def get_video_config(self) -> dict[str, Any]:
        config = self._load()
        video = config.get("video", {})
        defaults = DEFAULTS["video"]
        return _deep_merge(defaults, video)

    def set_video(self, key: str, value: Any) -> None:
        config = self._load()
        if "video" not in config:
            config["video"] = {}
        _set_nested(config["video"], key, value)
        self._save(config)

    def get_video_value(self, key: str, default: Any = None) -> Any:
        config = self.get_video_config()
        return _get_nested(config, key, default)

    def get_asset_library_config(self) -> dict[str, Any]:
        config = self._load()
        al = config.get("asset_library", {})
        defaults = DEFAULTS["asset_library"]
        return _deep_merge(defaults, al)

    def get_categories(self) -> list[CategoryConfig]:
        """Return the configured asset categories.

        Reads from ``asset_library.categories`` in ``app_config.json``.
        Falls back to the default food categories (matching the legacy ``Category`` enum)
        when the list is empty.
        """
        al_config = self.get_asset_library_config()
        raw: list[dict] = al_config.get("categories", [])
        if not raw:
            return default_categories()
        return [
            CategoryConfig(
                id=c.get("id", ""),
                name=c.get("name", ""),
                description=c.get("description", ""),
                vision_prompt=c.get("vision_prompt", ""),
            )
            for c in raw
        ]

    def get_category_suggestion_model(self) -> str:
        al_config = self.get_asset_library_config()
        return al_config.get("category_suggestion_model", "deepseek-v4-flash")

    def get_category_suggestion_sample_size(self) -> int:
        al_config = self.get_asset_library_config()
        return al_config.get("category_suggestion_sample_size", 20)
