from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TTSConfig:
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
    sample_rate: int | None = None
    bitrate: int | None = None
    channel: int | None = None
    enable_request_logging: bool | None = None
    enable_performance_metrics: bool | None = None
    log_audio_duration: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "voice": self.voice,
            "fallback_voice": self.fallback_voice,
            "randomize_voice": self.randomize_voice,
            "random_voices": self.random_voices,
            "voice_design_prompt": self.voice_design_prompt,
            "style_control_mode": self.style_control_mode,
            "style_prompt": self.style_prompt,
            "director_character": self.director_character,
            "director_scene": self.director_scene,
            "director_guidance": self.director_guidance,
            "audio_tags_enabled": self.audio_tags_enabled,
            "audio_tags": self.audio_tags,
            "voice_clone_sample_path": self.voice_clone_sample_path,
            "voice_clone_mime_type": self.voice_clone_mime_type,
            "optimize_text_preview": self.optimize_text_preview,
            "instructions": self.instructions,
            "optimize_instructions": self.optimize_instructions,
            "language_type": self.language_type,
            "audio_format": self.audio_format,
            "sample_rate": self.sample_rate,
            "bitrate": self.bitrate,
            "channel": self.channel,
            "enable_request_logging": self.enable_request_logging,
            "enable_performance_metrics": self.enable_performance_metrics,
            "log_audio_duration": self.log_audio_duration,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TTSConfig:
        return cls(
            model=data.get("model"),
            voice=data.get("voice"),
            fallback_voice=data.get("fallback_voice"),
            randomize_voice=data.get("randomize_voice"),
            random_voices=data.get("random_voices"),
            voice_design_prompt=data.get("voice_design_prompt"),
            style_control_mode=data.get("style_control_mode"),
            style_prompt=data.get("style_prompt"),
            director_character=data.get("director_character"),
            director_scene=data.get("director_scene"),
            director_guidance=data.get("director_guidance"),
            audio_tags_enabled=data.get("audio_tags_enabled"),
            audio_tags=data.get("audio_tags"),
            voice_clone_sample_path=data.get("voice_clone_sample_path"),
            voice_clone_mime_type=data.get("voice_clone_mime_type"),
            optimize_text_preview=data.get("optimize_text_preview", False),
            instructions=data.get("instructions"),
            optimize_instructions=data.get("optimize_instructions", False),
            language_type=data.get("language_type"),
            audio_format=data.get("audio_format"),
            sample_rate=data.get("sample_rate"),
            bitrate=data.get("bitrate"),
            channel=data.get("channel"),
            enable_request_logging=data.get("enable_request_logging"),
            enable_performance_metrics=data.get("enable_performance_metrics"),
            log_audio_duration=data.get("log_audio_duration"),
        )

    def with_defaults(self) -> TTSConfig:
        defaults = TTSConfigManager.DEFAULTS
        return TTSConfig(
            model=self.model if self.model is not None else defaults["model"],
            voice=self.voice if self.voice is not None else defaults["voice"],
            fallback_voice=self.fallback_voice if self.fallback_voice is not None else defaults["fallback_voice"],
            randomize_voice=self.randomize_voice if self.randomize_voice is not None else defaults["randomize_voice"],
            random_voices=self.random_voices if self.random_voices is not None else defaults["random_voices"],
            voice_design_prompt=self.voice_design_prompt if self.voice_design_prompt is not None else defaults["voice_design_prompt"],
            style_control_mode=self.style_control_mode if self.style_control_mode is not None else defaults["style_control_mode"],
            style_prompt=self.style_prompt if self.style_prompt is not None else defaults["style_prompt"],
            director_character=self.director_character if self.director_character is not None else defaults["director_character"],
            director_scene=self.director_scene if self.director_scene is not None else defaults["director_scene"],
            director_guidance=self.director_guidance if self.director_guidance is not None else defaults["director_guidance"],
            audio_tags_enabled=self.audio_tags_enabled if self.audio_tags_enabled is not None else defaults["audio_tags_enabled"],
            audio_tags=self.audio_tags if self.audio_tags is not None else defaults["audio_tags"],
            voice_clone_sample_path=self.voice_clone_sample_path,
            voice_clone_mime_type=self.voice_clone_mime_type,
            optimize_text_preview=self.optimize_text_preview,
            instructions=self.instructions if self.instructions is not None else defaults["instructions"],
            optimize_instructions=self.optimize_instructions,
            language_type=self.language_type if self.language_type is not None else defaults["language_type"],
            audio_format=self.audio_format if self.audio_format is not None else defaults["audio_format"],
            sample_rate=self.sample_rate if self.sample_rate is not None else defaults["sample_rate"],
            bitrate=self.bitrate if self.bitrate is not None else defaults["bitrate"],
            channel=self.channel if self.channel is not None else defaults["channel"],
            enable_request_logging=self.enable_request_logging if self.enable_request_logging is not None else defaults["enable_request_logging"],
            enable_performance_metrics=self.enable_performance_metrics if self.enable_performance_metrics is not None else defaults["enable_performance_metrics"],
            log_audio_duration=self.log_audio_duration if self.log_audio_duration is not None else defaults["log_audio_duration"],
        )


class TTSConfigManager:
    DEFAULTS: dict[str, Any] = {
        "model": "mimo-v2.5-tts",
        "voice": "Mia",
        "fallback_voice": "Dean",
        "randomize_voice": True,
        "random_voices": ["Mia", "Dean"],
        "voice_design_prompt": "",
        "style_control_mode": "simple",
        "style_prompt": "自然 清晰 适合短视频带货口播",
        "director_character": "",
        "director_scene": "",
        "director_guidance": "",
        "audio_tags_enabled": False,
        "audio_tags": "",
        "optimize_text_preview": False,
        "instructions": "",
        "optimize_instructions": False,
        "language_type": "Chinese",
        "audio_format": "wav",
        "sample_rate": None,
        "bitrate": None,
        "channel": None,
        "enable_request_logging": False,
        "enable_performance_metrics": True,
        "log_audio_duration": True,
    }

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

    def get_config(self, project_id: str | None = None) -> TTSConfig:
        global_config = self._load_config(None)
        if project_id:
            project_config = self._load_config(project_id)
            result = self._merge_configs(global_config, project_config).with_defaults()
        else:
            result = global_config.with_defaults()
        # 自动迁移: mimo-v2-tts → qwen3-tts-flash
        if result.model == "mimo-v2-tts":
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("Auto-migrating mimo-v2-tts → qwen3-tts-flash")
            result.model = "qwen3-tts-flash"
            result.voice = "Rocky"
        return result

    def _load_config(self, project_id: str | None = None) -> TTSConfig:
        if project_id is None:
            return self._load_global_config()
        return self._load_file_config(project_id)

    def _load_global_config(self) -> TTSConfig:
        from packages.provider_config.app_config import AppConfigManager
        app_manager = AppConfigManager(config_dir=self.config_dir)
        if app_manager.config_path.exists():
            data = app_manager.get_tts_config()
            return TTSConfig.from_dict(self._flatten_tts_config(data))
        file_path = self._get_config_path(None)
        if file_path.exists():
            with open(file_path, encoding="utf-8") as f:
                return TTSConfig.from_dict(json.load(f))
        return TTSConfig()

    def _load_file_config(self, project_id: str) -> TTSConfig:
        file_path = self._get_config_path(project_id)
        if file_path.exists():
            with open(file_path, encoding="utf-8") as f:
                return TTSConfig.from_dict(json.load(f))
        return TTSConfig()

    def save_config(self, config: TTSConfig, project_id: str | None = None) -> None:
        if project_id is None:
            self._save_global_config(config)
        else:
            self._save_file_config(config, project_id)

    def _save_global_config(self, config: TTSConfig) -> None:
        from packages.provider_config.app_config import AppConfigManager
        app_manager = AppConfigManager(config_dir=self.config_dir)
        for key, value in config.to_dict().items():
            if value is None:
                continue
            app_manager.set_tts(self._FLAT_TO_NESTED.get(key, key), value)

    def _save_file_config(self, config: TTSConfig, project_id: str) -> None:
        file_path = self._get_config_path(project_id)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)

    def _get_config_path(self, project_id: str | None = None) -> Path:
        if project_id:
            return self.config_dir / "projects" / project_id / "tts_config.json"
        return self.config_dir / "tts_config.json"

    @staticmethod
    def _merge_configs(*configs: TTSConfig) -> TTSConfig:
        if not configs:
            return TTSConfig()

        result = configs[0].to_dict()
        for config in configs[1:]:
            override = config.to_dict()
            for key, value in override.items():
                if value is not None and value != "" and value != []:
                    result[key] = value

        return TTSConfig.from_dict(result)

    @staticmethod
    def _flatten_tts_config(data: dict[str, Any]) -> dict[str, Any]:
        result = {}
        for key, value in data.items():
            if key == "director" and isinstance(value, dict):
                result["director_character"] = value.get("character", "")
                result["director_scene"] = value.get("scene", "")
                result["director_guidance"] = value.get("guidance", "")
            elif key == "audio_tags" and isinstance(value, dict):
                result["audio_tags_enabled"] = value.get("enabled", False)
                result["audio_tags"] = value.get("tags", "")
            elif key == "provider":
                continue
            else:
                result[key] = value
        return result
