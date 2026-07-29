"""Shared config constants and utilities used by both ``app_config`` and ``config_reader``.

This module exists solely to break the circular import between the two.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.provider_config.catalog import (
    default_runtime_provider_config,
    default_runtime_settings,
)


_PROVIDER_DEFAULTS = default_runtime_provider_config()
_SETTINGS_DEFAULTS = default_runtime_settings()

DEFAULTS: dict[str, Any] = {
    "llm": _PROVIDER_DEFAULTS["llm"],
    "tts": {
        **_PROVIDER_DEFAULTS["tts"],
        "fallback_voice": "Stella",
        "randomize_voice": True,
        "random_voices": ["Cherry", "Stella"],
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
    },
    "vision": _PROVIDER_DEFAULTS["vision"],
    "embedding": _SETTINGS_DEFAULTS["embedding"],
    "media": {
        **_SETTINGS_DEFAULTS["media"],
        "subtitle_mode": "script_timed",
        "max_retry": 3,
        "retry_delay_seconds": 60,
    },
    "asset_library": {
        **_SETTINGS_DEFAULTS["asset_library"],
        "categories": [],
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
    "scene": {
        **_SETTINGS_DEFAULTS["scene"],
    },
    "product": {
        "default_name": "",
        "default_brand": "",
        "script": {
            "scene": "",
            "material": "",
            "system_prompt": "你是一位短视频文案专家，撰写抖音口播文案。",
            "enable_qa_check": True,
            "word_count_min": 150,
            "word_count_max": 200,
            "max_sentence_length": 20,
            "forbidden_words": [
                "治疗",
                "治愈",
                "疗效",
                "降血糖",
                "降血压",
                "抗癌",
                "药到病除",
            ],
            "required_word_count": {
                "product": 1,
                "brand": 1,
            },
            "emoji_forbidden": True,
        },
        "categories": [],
        "keyword_map": {},
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
