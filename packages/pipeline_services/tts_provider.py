from __future__ import annotations

import random
from typing import Any

import requests

from packages.provider_config.secret_store import SecretStore
from packages.provider_config.config_constants import DEFAULTS


class TTSError(Exception):
    pass


class TTSRetryableError(TTSError):
    pass


class TTSBlockedError(TTSError):
    pass


class TTSQuotaExceededError(TTSBlockedError):
    pass


class TTSRetriesExhaustedError(TTSError):
    """Raised when per-sentence retries are exhausted.

    This sentinel tells the orchestrator not to escalate the failure into a
    phase-level retry, preventing a 3×3 retry storm (#266).
    """

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(f"TTS retries exhausted: {cause}")


class QwenTTSProvider:
    """百炼 Qwen-TTS 非实时语音合成 provider。

    调用 MultiModalConversation (/chat/completions) 接口，
    非流式返回音频 URL，下载后返回 bytes。
    """

    def __init__(
        self, api_key: str, base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _build_payload(self, text: str, config: Any) -> dict[str, Any]:
        input_data: dict[str, Any] = {
            "text": text,
            "voice": config.voice,
        }
        if getattr(config, "language_type", None):
            input_data["language_type"] = config.language_type
        instructions = getattr(config, "instructions", "")
        if instructions:
            input_data["instructions"] = instructions
            if getattr(config, "optimize_instructions", False):
                input_data["optimize_instructions"] = True
        return {
            "model": config.model,
            "input": input_data,
        }

    def _http_post(self, payload: dict[str, Any]) -> Any:
        url = f"{self.base_url}/services/aigc/multimodal-generation/generation"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=180,
            proxies={"http": None, "https": None},
        )

    def synthesize(self, text: str, config: Any) -> bytes:
        payload = self._build_payload(text, config)
        print(
            f"[TTS DEBUG] Qwen TTS: model={config.model} text_len={len(text)}",
            flush=True,
        )
        resp = self._http_post(payload)

        if resp.status_code == 429:
            raise TTSQuotaExceededError("TTS 配额超限")
        if resp.status_code in (401, 403):
            raise TTSBlockedError(f"TTS 鉴权失败: {resp.status_code}")
        if resp.status_code >= 400:
            detail = f"Qwen TTS HTTP {resp.status_code}"
            try:
                error_body = resp.json()
                msg = error_body.get("message", "")
                code = error_body.get("code", "")
                if msg:
                    detail = (
                        f"Qwen TTS error: {code} - {msg}"
                        if code
                        else f"Qwen TTS error: {msg}"
                    )
            except Exception:
                pass
            raise TTSBlockedError(detail)

        body = resp.json()
        code = body.get("code", "")
        if code and code != "":
            raise TTSBlockedError(f"Qwen TTS error: {code} - {body.get('message', '')}")

        audio_url = None
        output = body.get("output", {})
        if isinstance(output, dict):
            audio = output.get("audio", {})
            if isinstance(audio, dict):
                audio_url = audio.get("url")

        if not audio_url:
            raise TTSBlockedError("Qwen TTS 响应中未找到音频 URL")

        audio_resp = requests.get(audio_url, timeout=60)
        audio_resp.raise_for_status()
        return audio_resp.content


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
                {
                    "role": "user",
                    "content": config.voice_design_prompt or style_instruction,
                },
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

    def synthesize(self, text: str, config: Any) -> bytes:
        """完整 TTS 调用：构建请求 → HTTP → 解析响应 → 返回音频字节。"""
        payload = self._build_request(text, config)
        print(
            f"[TTS DEBUG] MiMo TTS: model={config.model} voice={config.voice}"
            f" text_len={len(text)}",
            flush=True,
        )
        url = f"{self.base_url}/chat/completions"
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=180,
            proxies={"http": None, "https": None},
        )

        if resp.status_code == 429:
            raise TTSQuotaExceededError("TTS 配额超限")
        if resp.status_code in (401, 403):
            raise TTSBlockedError(f"TTS 鉴权失败: {resp.status_code}")
        if resp.status_code >= 400:
            raise TTSBlockedError(f"MiMo TTS HTTP {resp.status_code}")

        try:
            body = resp.json()
        except (TypeError, ValueError):
            raise TTSBlockedError("MiMo TTS returned an invalid response") from None
        if not isinstance(body, dict):
            raise TTSBlockedError("MiMo TTS returned an invalid response")
        if "error" in body:
            msg = str(body["error"])
            if "quota" in msg.lower():
                raise TTSQuotaExceededError("MiMo TTS quota exceeded")
            raise TTSBlockedError("MiMo TTS request was rejected")

        audio = self._extract_audio(body)
        if not audio:
            raise TTSBlockedError("MiMo TTS response did not contain valid audio data")
        return audio

    @staticmethod
    def _extract_audio(body: dict[str, Any]) -> bytes | None:
        """递归搜索响应中的音频数据（base64 / hex / data URI）。"""
        import base64
        import binascii
        import re

        audio_keys = ("audio", "data", "b64_json", "base64")

        def _try_decode(value: Any) -> bytes | None:
            if not isinstance(value, str) or not value:
                return None

            if value.startswith("data:"):
                metadata, separator, encoded = value.partition(",")
                if not separator or not metadata.lower().endswith(";base64"):
                    return None
                try:
                    return base64.b64decode(encoded, validate=True)
                except (binascii.Error, ValueError):
                    return None

            try:
                return base64.b64decode(value, validate=True)
            except (binascii.Error, ValueError):
                pass

            hex_value = value[4:] if value.startswith("hex:") else value
            if len(hex_value) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", hex_value):
                try:
                    return bytes.fromhex(hex_value)
                except ValueError:
                    return None
            return None

        def _search(obj: Any) -> bytes | None:
            if isinstance(obj, dict):
                for key in audio_keys:
                    if key in obj:
                        candidate = obj[key]
                        result = _try_decode(candidate)
                        if result:
                            return result
                        if isinstance(candidate, (dict, list)):
                            result = _search(candidate)
                        if result:
                            return result
                for val in obj.values():
                    result = _search(val)
                    if result:
                        return result
            elif isinstance(obj, list):
                for item in obj:
                    result = _search(item)
                    if result:
                        return result
            return None

        return _search(body)


# ---------------------------------------------------------------------------
# TTS config shim (duck-type, preserves synthesize() API)
# ---------------------------------------------------------------------------


class TTSConfigShim:
    """Duck-type config object built from the TTS config dict.

    Preserves the interface expected by ``tts_provider.synthesize()``.
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        defaults = DEFAULTS["tts"]
        director = defaults.get("director", {})
        audio_tags = defaults.get("audio_tags", {})

        self.model: str = cfg.get("model", defaults["model"])
        self.voice: str = cfg.get("voice", defaults["voice"])
        self.instructions: str = cfg.get("instructions", defaults["instructions"])
        self.language_type: str = cfg.get("language_type", defaults["language_type"])
        self.optimize_instructions: bool = cfg.get("optimize_instructions", False)
        self.fallback_voice: str = cfg.get("fallback_voice", defaults["fallback_voice"])
        self.randomize_voice: bool = cfg.get("randomize_voice", defaults["randomize_voice"])
        self.random_voices: list[str] = cfg.get("random_voices", defaults["random_voices"])
        self.style_control_mode: str = cfg.get("style_control_mode", defaults["style_control_mode"])
        self.style_prompt: str = cfg.get("style_prompt", defaults["style_prompt"])
        self.voice_design_prompt: str = cfg.get("voice_design_prompt", defaults.get("voice_design_prompt", ""))
        self.audio_format: str = cfg.get("audio_format", defaults["audio_format"])
        self.audio_tags_enabled: bool = cfg.get("audio_tags_enabled", audio_tags.get("enabled", False))
        self.audio_tags: str = cfg.get("audio_tags", audio_tags.get("tags", ""))
        self.voice_clone_sample_path: str = cfg.get("voice_clone_sample_path", "")
        self.voice_clone_mime_type: str = cfg.get("voice_clone_mime_type", "")
        self.optimize_text_preview: bool = cfg.get("optimize_text_preview", False)
        self.director_character: str = cfg.get("director_character", director.get("character", ""))
        self.director_scene: str = cfg.get("director_scene", director.get("scene", ""))
        self.director_guidance: str = cfg.get("director_guidance", director.get("guidance", ""))


# ---------------------------------------------------------------------------
# TTS provider factory
# ---------------------------------------------------------------------------


def create_tts_provider(
    config: dict[str, Any], secrets: SecretStore
) -> QwenTTSProvider | MiMoTTSProvider:
    """Build a TTS provider instance from the current config dict.

    Model prefix ``qwen`` selects ``QwenTTSProvider``; everything else selects
    ``MiMoTTSProvider``. API keys and base URLs are resolved via ``SecretStore``
    so configuration changes take effect without restarting the worker.
    """
    tts_model = config.get("model", DEFAULTS["tts"]["model"]) or ""

    if tts_model.startswith("qwen"):
        base_url = secrets.get_api_base_url("qwen")
        if not base_url:
            base_url = "https://dashscope.aliyuncs.com/api/v1"
        return QwenTTSProvider(api_key=secrets.get_api_key("qwen"), base_url=base_url)

    base_url = secrets.get_api_base_url("mimo")
    if not base_url:
        base_url = "https://api.xiaomimimo.com/v1"
    return MiMoTTSProvider(api_key=secrets.get_api_key("mimo"), base_url=base_url)
