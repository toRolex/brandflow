from __future__ import annotations

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
        return self._build_preset_request(text, config, voice_id)

    def _build_preset_request(
        self,
        text: str,
        config: Any,
        voice_id: str | None = None,
    ) -> dict[str, Any]:
        voice = voice_id or config.voice
        style_instruction = (
            f"请用{config.style_prompt}的语气合成语音。"
            if config.style_prompt
            else "请用自然、清晰的语气合成语音。"
        )

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "user", "content": style_instruction},
                {"role": "assistant", "content": text},
            ],
            "audio": {
                "format": config.audio_format,
                "voice": voice,
            },
            "stream": False,
        }

        if config.sample_rate:
            payload["audio"]["sample_rate"] = config.sample_rate
        if config.bitrate:
            payload["audio"]["bitrate"] = config.bitrate
        if config.channel:
            payload["audio"]["channel"] = config.channel

        return payload

    def _build_voicedesign_request(
        self,
        text: str,
        config: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "user", "content": config.voice_design_prompt},
                {"role": "assistant", "content": text},
            ],
            "audio": {
                "format": config.audio_format,
            },
            "stream": False,
        }

        if config.sample_rate:
            payload["audio"]["sample_rate"] = config.sample_rate
        if config.bitrate:
            payload["audio"]["bitrate"] = config.bitrate
        if config.channel:
            payload["audio"]["channel"] = config.channel

        return payload
