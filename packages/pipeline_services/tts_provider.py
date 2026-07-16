from __future__ import annotations

import random
from typing import Any

import requests

from packages.provider_config.secret_store import SecretStore


class TTSError(Exception):
    pass


class TTSRetryableError(TTSError):
    pass


class TTSBlockedError(TTSError):
    pass


class TTSQuotaExceededError(TTSBlockedError):
    pass


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
        resp = self._http_post(payload)

        if resp.status_code == 429:
            raise TTSQuotaExceededError("TTS 配额超限")
        if resp.status_code in (401, 403):
            raise TTSBlockedError(f"TTS 鉴权失败: {resp.status_code}")
        resp.raise_for_status()

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
        resp.raise_for_status()

        body = resp.json()
        if "error" in body:
            msg = str(body["error"])
            if "quota" in msg.lower():
                raise TTSQuotaExceededError(msg)
            raise TTSBlockedError(msg)

        audio = self._extract_audio(body)
        if not audio:
            raise TTSBlockedError("TTS 响应中未找到音频数据")
        return audio

    @staticmethod
    def _extract_audio(body: dict) -> bytes | None:
        """递归搜索响应中的音频数据（base64 / hex / data URI）。"""
        import base64

        def _search(obj):
            if isinstance(obj, dict):
                for key in ("audio", "data", "b64_json", "base64"):
                    if key in obj:
                        result = _try_decode(str(obj[key]))
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

        def _try_decode(s: str) -> bytes | None:
            if not s or len(s) < 10:
                return None
            if s.startswith("data:"):
                _, encoded = s.split(",", 1)
                return base64.b64decode(encoded)
            try:
                return base64.b64decode(s)
            except Exception:
                pass
            try:
                return bytes.fromhex(s)
            except (ValueError, AttributeError):
                pass
            return None

        return _search(body)


# ---------------------------------------------------------------------------
# TTS config shim (duck-type, preserves synthesize() API)
# ---------------------------------------------------------------------------


class _TTSConfigShim:
    """Duck-type config object built from the TTS config dict.

    Preserves the interface expected by ``tts_provider.synthesize()``.
    """

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.model: str = cfg.get("model", "mimo-v2.5-tts")
        self.voice: str = cfg.get("voice", "Mia")
        self.instructions: str = cfg.get("instructions", "")
        self.language_type: str = cfg.get("language_type", "")
        self.optimize_instructions: bool = cfg.get("optimize_instructions", False)
        self.fallback_voice: str = cfg.get("fallback_voice", "Dean")
        self.randomize_voice: bool = cfg.get("randomize_voice", False)
        self.random_voices: list[str] = cfg.get("random_voices", ["Mia", "Dean"])
        self.style_control_mode: str = cfg.get("style_control_mode", "simple")
        self.style_prompt: str = cfg.get("style_prompt", "自然 清晰")
        self.voice_design_prompt: str = cfg.get("voice_design_prompt", "")
        self.audio_format: str = cfg.get("audio_format", "wav")
        self.audio_tags_enabled: bool = cfg.get("audio_tags_enabled", False)
        self.audio_tags: str = cfg.get("audio_tags", "")
        self.voice_clone_sample_path: str = cfg.get("voice_clone_sample_path", "")
        self.voice_clone_mime_type: str = cfg.get("voice_clone_mime_type", "")
        self.optimize_text_preview: bool = cfg.get("optimize_text_preview", False)
        self.director_character: str = cfg.get("director_character", "")
        self.director_scene: str = cfg.get("director_scene", "")
        self.director_guidance: str = cfg.get("director_guidance", "")


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
    tts_model = config.get("model", "mimo-v2.5-tts") or ""

    if tts_model.startswith("qwen"):
        base_url = secrets.get_api_base_url("qwen")
        if not base_url:
            base_url = "https://dashscope.aliyuncs.com/api/v1"
        return QwenTTSProvider(api_key=secrets.get_api_key("qwen"), base_url=base_url)

    base_url = secrets.get_api_base_url("mimo")
    if not base_url:
        base_url = "https://api.xiaomimimo.com/v1"
    return MiMoTTSProvider(api_key=secrets.get_api_key("mimo"), base_url=base_url)
