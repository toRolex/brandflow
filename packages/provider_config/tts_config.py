from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from packages.provider_config.config_constants import DEFAULTS


def _flatten_tts_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested storage keys (director/audio_tags) to flat field names."""
    result = {}
    for key, value in data.items():
        if key == "director" and isinstance(value, dict):
            result["director_character"] = value.get("character", "")
            result["director_scene"] = value.get("scene", "")
            result["director_guidance"] = value.get("guidance", "")
        elif key == "audio_tags" and isinstance(value, dict):
            result["audio_tags_enabled"] = value.get("enabled", False)
            result["audio_tags"] = value.get("tags", "")
        else:
            result[key] = value
    return result


# Fields that never receive global defaults: per-provider connection params
# (resolved downstream per selected provider) and per-upload clone artifacts.
_PASSTHROUGH_FIELDS = frozenset(
    {
        "voice_clone_sample_path",
        "voice_clone_mime_type",
        "speed",
        "vol",
        "pitch",
        "emotion",
        "sample_rate",
        "bitrate",
        "channel",
        "group_id",
        "endpoint",
        "extra_headers",
    }
)


@dataclass
class TTSConfig:
    provider: str | None = None
    model: str | None = None
    voice: str | None = None
    fallback_voice: str | None = None
    randomize_voice: bool | None = None
    random_voices: list[str] | None = None
    voice_design_prompt: str | None = None

    # 风格控制 - 自然语言控制
    style_control_mode: str | None = None  # "simple" 或 "director"
    style_prompt: str | None = None  # 简单模式的风格描述

    # 导演模式
    director_character: str | None = None  # 角色描述
    director_scene: str | None = None  # 场景描述
    director_guidance: str | None = None  # 指导描述

    # 标签控制
    audio_tags_enabled: bool | None = None  # 是否启用标签控制
    audio_tags: str | None = None  # 音频标签，如 "(温柔)[笑声]文本内容[叹气]"

    # 音色克隆
    voice_clone_sample_path: str | None = None
    voice_clone_mime_type: str | None = None

    # 文本优化预览（仅适用于 voicedesign 模型）
    optimize_text_preview: bool = False

    # Qwen-TTS 专属字段
    instructions: str | None = None  # 指令控制文本
    optimize_instructions: bool = False  # 是否优化指令
    language_type: str | None = None  # 语种 (Auto/Chinese/English/...)

    audio_format: str | None = None

    # Provider 连接参数 (#386)
    speed: str | None = None
    vol: str | None = None
    pitch: str | None = None
    emotion: str | None = None
    sample_rate: str | None = None
    bitrate: str | None = None
    channel: str | None = None
    group_id: str | None = None
    endpoint: str | None = None
    extra_headers: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TTSConfig:
        # Unknown keys (e.g. removed legacy fields) are silently ignored;
        # missing keys keep their dataclass defaults.  Numeric config values
        # (sample_rate: 44100) are coerced so string fields stay valid.
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            value = data.get(f.name)
            if value is None:
                continue
            if f.type == "str | None" and isinstance(value, (int, float)):
                value = str(value)
            kwargs[f.name] = value
        return cls(**kwargs)

    def with_defaults(self) -> TTSConfig:
        flat_defaults = _flatten_tts_dict(DEFAULTS["tts"])
        merged = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None and f.name not in _PASSTHROUGH_FIELDS:
                value = flat_defaults.get(f.name)
            merged[f.name] = value
        return TTSConfig.from_dict(merged)


class TTSConfigManager:
    _FLAT_TO_NESTED = {
        "director_character": "director.character",
        "director_scene": "director.scene",
        "director_guidance": "director.guidance",
        "audio_tags_enabled": "audio_tags.enabled",
        "audio_tags": "audio_tags.tags",
    }

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get_config(self, product_id: str | None = None) -> TTSConfig:
        if product_id:
            return self._load_product_config(product_id).with_defaults()
        return self._load_global_config().with_defaults()

    def _load_global_config(self) -> TTSConfig:
        from packages.provider_config.config_reader import ConfigReader

        reader = ConfigReader(config_dir=str(self.config_dir))
        data = reader.get_tts_config()  # 不带 product_id → 顶层 tts
        return TTSConfig.from_dict(_flatten_tts_dict(data))

    def _load_product_config(self, product_id: str) -> TTSConfig:
        from packages.provider_config.config_reader import ConfigReader

        reader = ConfigReader(config_dir=str(self.config_dir))
        data = reader.get_tts_config(product_id=product_id)
        return TTSConfig.from_dict(_flatten_tts_dict(data))

    def save_config(self, config: TTSConfig, product_id: str | None = None) -> None:
        if product_id is None:
            self._save_global_config(config)
        else:
            self._save_product_config(config, product_id)

    def _save_global_config(self, config: TTSConfig) -> None:
        from packages.provider_config.config_io import load_config, save_config
        from packages.provider_config.config_constants import _set_nested

        config_path = self.config_dir / "app_config.json"
        raw = load_config(config_path)
        if "tts" not in raw:
            raw["tts"] = {}
        for key, value in config.to_dict().items():
            if value is None:
                continue
            _set_nested(raw["tts"], self._FLAT_TO_NESTED.get(key, key), value)
        save_config(config_path, raw)

    def _save_product_config(self, config: TTSConfig, product_id: str) -> None:
        from packages.provider_config.config_io import load_config, save_config
        from packages.provider_config.config_constants import _set_nested

        config_path = self.config_dir / "app_config.json"
        raw = load_config(config_path)
        # 找到匹配 product，不存在则创建
        for i, p in enumerate(raw.get("products", [])):
            if p.get("id") == product_id:
                if "tts" not in raw["products"][i]:
                    raw["products"][i]["tts"] = {}
                for key, value in config.to_dict().items():
                    if value is None:
                        continue
                    _set_nested(
                        raw["products"][i]["tts"],
                        self._FLAT_TO_NESTED.get(key, key),
                        value,
                    )
                save_config(config_path, raw)
                return
        # product 不存在，报错而非隐式创建
        raise ValueError(f"product '{product_id}' not found in app_config.json")


def resolve_tts_config(
    tts_dict: dict[str, Any],
    overrides: dict[str, Any] | None = None,
) -> TTSConfig:
    """Single runtime entry point: raw dict + optional overrides → TTSConfig.

    Applies overrides (e.g. job-level tts_model/tts_voice), infers the provider
    from the final model when it is not explicitly overridden, and fills defaults.

    A job-level model override drives provider selection so the runtime never
    routes a Qwen model through a MiMo provider (or vice-versa).
    """
    from packages.provider_config.catalog import tts_provider_for_model

    overrides = overrides or {}
    merged = {**tts_dict, **overrides}
    if not merged.get("provider") or (
        "model" in overrides and "provider" not in overrides
    ):
        inferred = tts_provider_for_model(str(merged.get("model") or ""))
        if inferred:
            merged["provider"] = inferred
    return TTSConfig.from_dict(_flatten_tts_dict(merged)).with_defaults()
