from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator


def _resolve_value(value: str) -> str:
    if value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value


LLM_ENV_MAPPINGS = {
    "deepseek": {
        "provider": "deepseek",
        "env": {
            "DEEPSEEK_API_KEY": "api_key",
            "DEEPSEEK_API_URL": "endpoint",
            "DEEPSEEK_MODEL": "model",
            "DEEPSEEK_THINKING": "thinking",
        },
    },
    "kimi": {
        "provider": "kimi",
        "env": {
            "KIMI_API_KEY": "api_key",
            "KIMI_API_URL": "endpoint",
            "KIMI_MODEL": "model",
        },
    },
    "openai": {
        "provider": "openai",
        "env": {
            "OPENAI_API_KEY": "api_key",
            "OPENAI_API_URL": "endpoint",
            "OPENAI_MODEL": "model",
        },
    },
    "custom": {
        "provider": "openai",
        "env": {
            "OPENAI_API_KEY": "api_key",
            "OPENAI_API_URL": "endpoint",
            "OPENAI_MODEL": "model",
        },
    },
}

TTS_ENV_MAPPINGS = {
    "qwen": {
        "provider": "qwen",
        "env": {
            "DASHSCOPE_API_KEY": "api_key",
            "DASHSCOPE_API_URL": "endpoint",
            "QWEN_TTS_MODEL": "model",
            "QWEN_TTS_VOICE": "voice",
            "QWEN_TTS_INSTRUCTIONS": "instructions",
            "QWEN_TTS_LANGUAGE_TYPE": "language_type",
            "QWEN_TTS_AUDIO_FORMAT": "audio_format",
        },
    },
    "mimo": {
        "provider": "mimo",
        "env": {
            "MIMO_API_KEY": "api_key",
            "MIMO_API_BASE_URL": "endpoint",
            "MIMO_TTS_MODEL": "model",
            "MIMO_TTS_VOICE": "voice",
            "MIMO_TTS_STYLE": "style",
            "MIMO_AUDIO_FORMAT": "audio_format",
        },
    },
    "minimax": {
        "provider": "minimax",
        "env": {
            "MINIMAX_API_KEY": "api_key",
            "MINIMAX_TTS_URL": "endpoint",
            "MINIMAX_GROUP_ID": "group_id",
            "MINIMAX_TTS_MODEL": "model",
            "MINIMAX_VOICE_ID": "voice_id",
            "MINIMAX_VOICE_SPEED": "speed",
            "MINIMAX_VOICE_VOL": "vol",
            "MINIMAX_VOICE_PITCH": "pitch",
            "MINIMAX_VOICE_EMOTION": "emotion",
            "MINIMAX_AUDIO_FORMAT": "audio_format",
            "MINIMAX_AUDIO_SAMPLE_RATE": "sample_rate",
            "MINIMAX_AUDIO_BITRATE": "bitrate",
            "MINIMAX_AUDIO_CHANNEL": "channel",
        },
    },
    "custom": {
        "provider": "custom",
        "env": {},
    },
}

VISION_ENV_MAPPINGS = {
    "xiaomi": {
        "provider": "xiaomi",
        "env": {
            "XIAOMI_VISION_API_KEY": "api_key",
            "XIAOMI_VISION_API_URL": "endpoint",
            "XIAOMI_VISION_MODEL": "model",
        },
    },
    "openai": {
        "provider": "openai",
        "env": {
            "VISION_API_KEY": "api_key",
            "VISION_API_URL": "endpoint",
            "VISION_MODEL": "model",
        },
    },
    "claude": {
        "provider": "claude",
        "env": {
            "VISION_API_KEY": "api_key",
            "VISION_API_URL": "endpoint",
            "VISION_MODEL": "model",
        },
    },
    "custom": {
        "provider": "custom",
        "env": {
            "VISION_API_KEY": "api_key",
            "VISION_API_URL": "endpoint",
            "VISION_MODEL": "model",
        },
    },
}


def ensure_supported_runtime_selection(payload: dict) -> None:
    if payload.get("providers", {}).get("tts", {}).get("selected") == "custom":
        raise ValueError("tts=custom 暂不支持当前阶段运行时执行")


def _section_overrides(selected: str, providers: dict, mappings: dict, provider_env_key: str) -> dict[str, str]:
    mapping = mappings.get(selected)
    if mapping is None:
        return {}
    provider_payload = providers.get(selected, {})
    overrides = {provider_env_key: mapping["provider"]}
    for env_name, field_name in mapping["env"].items():
        value = provider_payload.get(field_name, "")
        if not isinstance(value, str) or value == "":
            continue
        resolved = _resolve_value(value)
        if resolved == "":
            continue
        overrides[env_name] = resolved
    return overrides


def provider_env_overrides(payload: dict) -> dict[str, str]:
    ensure_supported_runtime_selection(payload)
    providers = payload.get("providers", {})
    overrides: dict[str, str] = {}
    overrides.update(
        _section_overrides(
            providers.get("llm", {}).get("selected", ""),
            providers.get("llm", {}).get("providers", {}),
            LLM_ENV_MAPPINGS,
            "LLM_PROVIDER",
        )
    )
    overrides.update(
        _section_overrides(
            providers.get("tts", {}).get("selected", ""),
            providers.get("tts", {}).get("providers", {}),
            TTS_ENV_MAPPINGS,
            "TTS_PROVIDER",
        )
    )
    overrides.update(
        _section_overrides(
            providers.get("vision", {}).get("selected", ""),
            providers.get("vision", {}).get("providers", {}),
            VISION_ENV_MAPPINGS,
            "VISION_PROVIDER",
        )
    )
    return overrides


@contextmanager
def temporary_env(overrides: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
