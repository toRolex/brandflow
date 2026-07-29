from __future__ import annotations

import logging
import random
import json
from typing import Any
from urllib.parse import urlparse

import requests

from packages.provider_config.catalog import (
    tts_provider_for_model,
    tts_runtime_providers,
)
from packages.provider_config.config_constants import DEFAULTS
from packages.provider_config.secret_store import SecretStore
from packages.provider_config.tts_config import TTSConfig

_LOGGER = logging.getLogger(__name__)


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

    _TTS_PATH: str = "/services/aigc/multimodal-generation/generation"

    def __init__(
        self, api_key: str, base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    ):
        self.api_key = api_key
        base_url = base_url.rstrip("/")
        # 保留用户配置的 base_url；若配置中已包含完整 API 路径，不再重复拼接。
        self.base_url = base_url
        if base_url.endswith(self._TTS_PATH):
            self._endpoint_url = base_url
        else:
            self._endpoint_url = f"{base_url}{self._TTS_PATH}"

    def _build_payload(self, text: str, config: TTSConfig) -> dict[str, Any]:
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

    @staticmethod
    def _extra_headers(config: TTSConfig) -> dict[str, str]:
        raw = config.extra_headers
        if not isinstance(raw, str) or not raw.strip():
            return {}
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(key): str(item) for key, item in value.items()}

    def _http_post(self, payload: dict[str, Any], config: TTSConfig) -> Any:
        headers = self._extra_headers(config)
        headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )
        return requests.post(
            self._endpoint_url,
            headers=headers,
            json=payload,
            timeout=180,
            proxies={"all": None, "http": None, "https": None},
        )

    def synthesize(self, text: str, config: TTSConfig) -> bytes:
        payload = self._build_payload(text, config)
        _LOGGER.debug(
            "[TTS DEBUG] Qwen TTS: model=%s text_len=%s",
            config.model,
            len(text),
        )
        resp = self._http_post(payload, config)

        if resp.status_code == 429:
            raise TTSQuotaExceededError("TTS 配额超限")
        if resp.status_code in (401, 403):
            raise TTSBlockedError(
                f"TTS 鉴权失败: {resp.status_code} ← {self._endpoint_url}"
            )
        if resp.status_code >= 400:
            detail = f"Qwen TTS HTTP {resp.status_code} ← {self._endpoint_url}"
            try:
                error_body = resp.json()
                msg = error_body.get("message", "")
                code = error_body.get("code", "")
                if msg:
                    detail = (
                        f"Qwen TTS error: {code} - {msg} ← {self._endpoint_url}"
                        if code
                        else f"Qwen TTS error: {msg} ← {self._endpoint_url}"
                    )
            except Exception:
                body = resp.text or "(empty body)"
                detail = f"{detail}, body={body[:200]}"
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

        audio_resp = requests.get(
            audio_url,
            timeout=60,
            proxies={"all": None, "http": None, "https": None},
        )
        audio_resp.raise_for_status()
        return audio_resp.content


class MiMoTTSProvider:
    # 默认 TTS endpoint（完整 URL，含路径）。当外部只提供 base URL 时拼接此路径。
    _DEFAULT_TTS_PATH: str = "/chat/completions"

    def __init__(self, api_key: str, base_url: str = "https://api.xiaomimimo.com/v1"):
        self.api_key = api_key
        base_url = base_url.rstrip("/")
        # 若 endpoint 已包含具体 API 路径（如 /chat/completions、/audio/speech），
        # 直接作为完整 URL 使用，避免重复拼接；否则追加默认路径。
        try:
            resolved = urlparse(base_url)
            path = resolved.path
        except (TypeError, ValueError, AttributeError):
            path = ""
        if path and path not in ("/", "/v1"):
            self.base_url = base_url
        else:
            self.base_url = f"{base_url}{self._DEFAULT_TTS_PATH}"

    def _build_request(
        self,
        text: str,
        config: TTSConfig,
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

    def _build_style_instruction(self, config: TTSConfig) -> str:
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

    def _build_assistant_content(self, text: str, config: TTSConfig) -> str:
        # 标签控制：在文本前添加标签
        if config.audio_tags_enabled and config.audio_tags:
            return f"{config.audio_tags}{text}"
        return text

    @staticmethod
    def _apply_provider_params(payload: dict[str, Any], config: TTSConfig) -> None:
        """Inject provider connection parameters into the request payload (#386)."""
        audio = payload.setdefault("audio", {})
        for config_key, payload_key in (
            ("group_id", "group_id"),
            ("speed", "speed"),
            ("vol", "volume"),
            ("pitch", "pitch"),
            ("emotion", "emotion"),
        ):
            value = getattr(config, config_key, None)
            if isinstance(value, str) and value:
                payload[payload_key] = value
        for key in ("sample_rate", "bitrate", "channel"):
            value = getattr(config, key, None)
            if isinstance(value, str) and value:
                audio[key] = value

    def _build_preset_request(
        self,
        text: str,
        config: TTSConfig,
        voice_id: str | None = None,
    ) -> dict[str, Any]:
        voice = voice_id or config.voice
        style_instruction = self._build_style_instruction(config)
        assistant_content = self._build_assistant_content(text, config)

        audio: dict[str, Any] = {
            "format": config.audio_format,
            "voice": voice,
        }
        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {"role": "user", "content": style_instruction},
                {"role": "assistant", "content": assistant_content},
            ],
            "audio": audio,
            "stream": False,
        }
        self._apply_provider_params(payload, config)
        return payload

    def _build_voicedesign_request(
        self,
        text: str,
        config: TTSConfig,
    ) -> dict[str, Any]:
        style_instruction = self._build_style_instruction(config)
        assistant_content = self._build_assistant_content(text, config)

        audio: dict[str, Any] = {
            "format": config.audio_format,
        }
        if config.optimize_text_preview:
            audio["optimize_text_preview"] = True

        payload: dict[str, Any] = {
            "model": config.model,
            "messages": [
                {
                    "role": "user",
                    "content": config.voice_design_prompt or style_instruction,
                },
                {"role": "assistant", "content": assistant_content},
            ],
            "audio": audio,
            "stream": False,
        }

        self._apply_provider_params(payload, config)
        return payload

    def _build_voiceclone_request(
        self,
        text: str,
        config: TTSConfig,
    ) -> dict[str, Any]:
        """构建 voiceclone 请求

        voice 字段格式：data:{mime_type};base64,{base64_audio}
        """
        import base64
        from pathlib import Path

        if not config.voice_clone_sample_path:
            raise TTSError("Voice clone sample path is not configured")
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
        self._apply_provider_params(payload, config)
        return payload

    def synthesize(self, text: str, config: TTSConfig) -> bytes:
        """完整 TTS 调用：构建请求 → HTTP → 解析响应 → 返回音频字节。"""
        payload = self._build_request(text, config)
        _LOGGER.debug(
            "[TTS DEBUG] MiMo TTS: model=%s voice=%s text_len=%s",
            config.model,
            config.voice,
            len(text),
        )
        url = self.base_url  # 已在 __init__ 中解析为完整 endpoint URL
        headers = QwenTTSProvider._extra_headers(config)
        headers.update(
            {
                "api-key": self.api_key,
                "Content-Type": "application/json",
            }
        )
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=180,
            proxies={"all": None, "http": None, "https": None},
        )

        if resp.status_code == 429:
            raise TTSQuotaExceededError("TTS 配额超限")
        if resp.status_code in (401, 403):
            raise TTSBlockedError(f"TTS 鉴权失败: {resp.status_code}")
        if resp.status_code >= 400:
            detail = f"MiMo TTS HTTP {resp.status_code} ← {url}"
            raise TTSBlockedError(detail)

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
# TTS provider factory
# ---------------------------------------------------------------------------


def resolve_tts_provider_name(config: TTSConfig) -> str:
    """Return and validate the provider selected by a TTS config."""
    tts_model = str(config.model or DEFAULTS["tts"]["model"])
    configured_provider = (config.provider or "").strip().lower()
    inferred_provider = tts_provider_for_model(tts_model)
    if configured_provider:
        provider_name = configured_provider
    elif inferred_provider:
        provider_name = inferred_provider
    else:
        provider_name = str(DEFAULTS["tts"]["provider"])

    if provider_name not in tts_runtime_providers():
        raise ValueError(f"Unsupported TTS provider: {provider_name}")
    if tts_model and inferred_provider != provider_name:
        raise ValueError(
            f"TTS provider/model mismatch: provider={provider_name}, model={tts_model}"
        )
    return provider_name


def create_tts_provider(
    config: TTSConfig, secrets: SecretStore
) -> QwenTTSProvider | MiMoTTSProvider:
    """Build a TTS provider instance from a TTSConfig.

    ``provider`` is authoritative.  Model-prefix inference is retained only for
    legacy callers that do not yet supply a provider.  A contradictory
    provider/model pair is rejected instead of silently routing to a different
    provider.
    """
    provider_name = resolve_tts_provider_name(config)

    configured_endpoint = (config.endpoint or "").strip().rstrip("/")
    if provider_name == "qwen":
        base_url = configured_endpoint or secrets.get_api_base_url(
            "qwen", section="tts"
        )
        if not base_url:
            base_url = "https://dashscope.aliyuncs.com/api/v1"
        return QwenTTSProvider(
            api_key=secrets.get_api_key("qwen", section="tts"), base_url=base_url
        )

    base_url = configured_endpoint or secrets.get_api_base_url("mimo", section="tts")
    if not base_url:
        base_url = "https://api.xiaomimimo.com/v1"
    return MiMoTTSProvider(
        api_key=secrets.get_api_key("mimo", section="tts"), base_url=base_url
    )
