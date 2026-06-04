from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TTSConfig:
    model: str = "mimo-v2.5-tts"
    voice: str = "Mia"
    fallback_voice: str = "Dean"
    randomize_voice: bool = True
    random_voices: list[str] = field(default_factory=lambda: ["Mia", "Dean"])
    voice_design_prompt: str = ""
    style_prompt: str = "自然 清晰 适合短视频带货口播"
    audio_format: str = "mp3"
    sample_rate: int | None = None
    bitrate: int | None = None
    channel: int | None = None
    enable_request_logging: bool = False
    enable_performance_metrics: bool = True
    log_audio_duration: bool = True

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
            model=data.get("model", "mimo-v2.5-tts"),
            voice=data.get("voice", "Mia"),
            fallback_voice=data.get("fallback_voice", "Dean"),
            randomize_voice=data.get("randomize_voice", True),
            random_voices=data.get("random_voices", ["Mia", "Dean"]),
            voice_design_prompt=data.get("voice_design_prompt", ""),
            style_prompt=data.get("style_prompt", "自然 清晰 适合短视频带货口播"),
            audio_format=data.get("audio_format", "mp3"),
            sample_rate=data.get("sample_rate"),
            bitrate=data.get("bitrate"),
            channel=data.get("channel"),
            enable_request_logging=data.get("enable_request_logging", False),
            enable_performance_metrics=data.get("enable_performance_metrics", True),
            log_audio_duration=data.get("log_audio_duration", True),
        )


class TTSConfigManager:
    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def get_config(self, project_id: str | None = None) -> TTSConfig:
        file_path = self._get_config_path(project_id)
        if file_path.exists():
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return TTSConfig.from_dict(data)
        return TTSConfig()

    def save_config(self, config: TTSConfig, project_id: str | None = None) -> None:
        file_path = self._get_config_path(project_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)

    def _get_config_path(self, project_id: str | None = None) -> Path:
        if project_id:
            return self.config_dir / f"tts_config_{project_id}.json"
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
