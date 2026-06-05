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
    style_prompt: str | None = None
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
            "style_prompt": self.style_prompt,
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
            style_prompt=data.get("style_prompt"),
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
            style_prompt=self.style_prompt if self.style_prompt is not None else defaults["style_prompt"],
            audio_format=self.audio_format if self.audio_format is not None else defaults["audio_format"],
            sample_rate=self.sample_rate if self.sample_rate is not None else defaults["sample_rate"],
            bitrate=self.bitrate if self.bitrate is not None else defaults["bitrate"],
            channel=self.channel if self.channel is not None else defaults["channel"],
            enable_request_logging=self.enable_request_logging if self.enable_request_logging is not None else defaults["enable_request_logging"],
            enable_performance_metrics=self.enable_performance_metrics if self.enable_performance_metrics is not None else defaults["enable_performance_metrics"],
            log_audio_duration=self.log_audio_duration if self.log_audio_duration is not None else defaults["log_audio_duration"],
        )


class TTSConfigManager:
    DEFAULTS = {
        "model": "mimo-v2.5-tts",
        "voice": "Mia",
        "fallback_voice": "Dean",
        "randomize_voice": True,
        "random_voices": ["Mia", "Dean"],
        "voice_design_prompt": "",
        "style_prompt": "自然 清晰 适合短视频带货口播",
        "audio_format": "mp3",
        "sample_rate": None,
        "bitrate": None,
        "channel": None,
        "enable_request_logging": False,
        "enable_performance_metrics": True,
        "log_audio_duration": True,
    }

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get_config(self, project_id: str | None = None) -> TTSConfig:
        global_config = self._load_config(None)
        if project_id:
            project_config = self._load_config(project_id)
            return self._merge_configs(global_config, project_config).with_defaults()
        return global_config.with_defaults()

    def _load_config(self, project_id: str | None = None) -> TTSConfig:
        file_path = self._get_config_path(project_id)
        if file_path.exists():
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return TTSConfig.from_dict(data)
        return TTSConfig()

    def save_config(self, config: TTSConfig, project_id: str | None = None) -> None:
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
