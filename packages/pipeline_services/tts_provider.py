from __future__ import annotations

import random
from typing import Any


class TTSError(Exception):
    pass


class TTSRetryableError(TTSError):
    pass


class TTSBlockedError(TTSError):
    pass


class TTSQuotaExceededError(TTSBlockedError):
    pass


class MiMoTTSProvider:
    def __init__(self, api_key: str, base_url: str = "https://api.xiaomimimo.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _build_request(
        self,
        text: str,
        config: Any,
        voice_id: str | None = None,
    ) -> dict[str, Any]:
        if config.model == "mimo-v2.5-tts-voicedesign":
            return self._build_voicedesign_request(text, config)
        if config.model == "mimo-v2.5-tts-voiceclone":
            return self._build_voiceclone_request(text, config)
        voice = voice_id or config.voice
        if config.randomize_voice and config.random_voices:
            voice = random.choice(config.random_voices)
        return self._build_preset_request(text, config, voice)

    def _build_style_instruction(self, config: Any) -> str:
        # 导演模式
        if config.style_control_mode == "director":
            parts = []
            if config.director_character:
                parts.append(f"【角色】{config.director_character}")
            if config.director_scene:
                parts.append(f"【场景】{config.director_scene}")
            if config.director_guidance:
                parts.append(f"【指导】{config.director_guidance}")
            if parts:
                return "\n".join(parts)
        
        # 简单模式
        if config.style_prompt:
            return config.style_prompt
        
        return "自然 清晰 适合短视频带货口播"

    def _build_assistant_content(self, text: str, config: Any) -> str:
        # 标签控制：在文本前添加标签
        if config.audio_tags_enabled and config.audio_tags:
            return f"{config.audio_tags}{text}"
        return text

    def _build_preset_request(
        self,
        text: str,
        config: Any,
        voice_id: str | None = None,
    ) -> dict[str, Any]:
        voice = voice_id or config.voice
        style_instruction = self._build_style_instruction(config)
        assistant_content = self._build_assistant_content(text, config)

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "user", "content": style_instruction},
                {"role": "assistant", "content": assistant_content},
            ],
            "audio": {
                "format": config.audio_format,
                "voice": voice,
            },
            "stream": False,
        }

        return payload

    def _build_voicedesign_request(
        self,
        text: str,
        config: Any,
    ) -> dict[str, Any]:
        style_instruction = self._build_style_instruction(config)
        assistant_content = self._build_assistant_content(text, config)

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "user", "content": config.voice_design_prompt or style_instruction},
                {"role": "assistant", "content": assistant_content},
            ],
            "audio": {
                "format": config.audio_format,
            },
            "stream": False,
        }

        if getattr(config, "optimize_text_preview", False):
            payload["audio"]["optimize_text_preview"] = True

        return payload

    def _build_voiceclone_request(
        self,
        text: str,
        config: Any,
    ) -> dict[str, Any]:
        """构建 voiceclone 请求

        voice 字段格式：data:{mime_type};base64,{base64_audio}
        """
        import base64
        from pathlib import Path

        sample_path = Path(config.voice_clone_sample_path)
        if not sample_path.exists():
            raise TTSError(f"Voice clone sample not found: {sample_path}")

        audio_bytes = sample_path.read_bytes()
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")

        mime_type = config.voice_clone_mime_type or "audio/mpeg"
        voice_data_uri = f"data:{mime_type};base64,{b64_audio}"

        style_instruction = self._build_style_instruction(config)
        assistant_content = self._build_assistant_content(text, config)

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "user", "content": style_instruction},
                {"role": "assistant", "content": assistant_content},
            ],
            "audio": {
                "format": config.audio_format,
                "voice": voice_data_uri,
            },
            "stream": False,
        }

        return payload
