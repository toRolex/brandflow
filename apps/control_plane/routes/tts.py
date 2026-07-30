from __future__ import annotations

import io
import wave

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pathlib import Path
from pydantic import BaseModel

from packages.pipeline_services.media_utils import detect_audio_format
from packages.provider_config.catalog import tts_provider_for_model, tts_preset_voices
from packages.provider_config.config_constants import DEFAULTS
from packages.provider_config.secret_store import SecretStore
from packages.provider_config.tts_config import TTSConfigManager

router = APIRouter(prefix="/api/tts", tags=["tts"])

_secret_store = SecretStore()
app_config = _secret_store  # backward compatibility alias
config_manager = TTSConfigManager()


def _is_playable_wav(audio_bytes: bytes) -> bool:
    if len(audio_bytes) >= 12 and audio_bytes[:4] == b"RIFF":
        wav_bytes = bytearray(audio_bytes)
        riff_size = int.from_bytes(wav_bytes[4:8], "little")
        data_offset = wav_bytes.find(b"data", 12)
        if (
            riff_size == 0x7FFFFFBF
            and data_offset >= 0
            and data_offset + 8 <= len(wav_bytes)
            and int.from_bytes(wav_bytes[data_offset + 4 : data_offset + 8], "little")
            == riff_size - data_offset
        ):
            wav_bytes[4:8] = (len(wav_bytes) - 8).to_bytes(4, "little")
            wav_bytes[data_offset + 4 : data_offset + 8] = (
                len(wav_bytes) - data_offset - 8
            ).to_bytes(4, "little")
        audio_bytes = bytes(wav_bytes)

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
            frame_count = wav_file.getnframes()
            if frame_count <= 0 or wav_file.getframerate() <= 0:
                return False
            expected_size = (
                frame_count * wav_file.getnchannels() * wav_file.getsampwidth()
            )
            return len(wav_file.readframes(frame_count)) == expected_size
    except (EOFError, wave.Error):
        return False


class TTSConfigRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    voice: str | None = None
    fallback_voice: str | None = None
    randomize_voice: bool | None = None
    random_voices: list[str] | None = None
    voice_design_prompt: str | None = None
    style_control_mode: str | None = None
    style_prompt: str | None = None
    director_character: str | None = None
    director_scene: str | None = None
    director_guidance: str | None = None
    audio_tags_enabled: bool | None = None
    audio_tags: str | None = None
    audio_format: str | None = None
    # Qwen-TTS fields
    instructions: str | None = None
    optimize_instructions: bool | None = None
    language_type: str | None = None
    # VoiceClone / VoiceDesign fields
    voice_clone_sample_path: str | None = None
    voice_clone_mime_type: str | None = None
    optimize_text_preview: bool | None = None
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


class TTSConfigResponse(BaseModel):
    provider: str
    model: str
    voice: str
    fallback_voice: str
    randomize_voice: bool
    random_voices: list[str]
    voice_design_prompt: str
    style_control_mode: str
    style_prompt: str
    director_character: str
    director_scene: str
    director_guidance: str
    audio_tags_enabled: bool
    audio_tags: str
    audio_format: str
    # Qwen-TTS fields
    instructions: str
    optimize_instructions: bool
    language_type: str
    # VoiceClone / VoiceDesign fields
    voice_clone_sample_path: str | None
    voice_clone_mime_type: str | None
    optimize_text_preview: bool
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


class TTSPreviewRequest(BaseModel):
    text: str
    provider: str | None = None
    model: str | None = None
    voice: str | None = None
    style_prompt: str | None = None
    voice_design_prompt: str | None = None
    # Qwen-TTS fields
    instructions: str | None = None
    optimize_instructions: bool | None = None
    language_type: str | None = None
    # Keep preview requests aligned with the persisted TTS form state.
    speed: str | None = None
    vol: str | None = None
    pitch: str | None = None
    emotion: str | None = None
    group_id: str | None = None
    endpoint: str | None = None
    sample_rate: str | None = None
    bitrate: str | None = None
    channel: str | None = None
    extra_headers: str | None = None


# Voice lists moved to catalog.json preset_voices (#386)
_INSTRUCT_UNSUPPORTED_VOICES = {"Jennifer", "Ryan", "Katerina"}


@router.get("/config", response_model=TTSConfigResponse)
async def get_tts_config(product_id: str | None = None):
    config = config_manager.get_config(product_id)
    return TTSConfigResponse(**config.to_dict())


@router.get("/models")
async def get_tts_models():
    """Catalog-driven model cards and per-provider connection fields (#386)."""
    from packages.provider_config.catalog import (
        tts_connection_fields,
        tts_models,
        tts_runtime_providers,
    )

    return {
        "models": tts_models(),
        "connection_fields": {
            provider: tts_connection_fields(provider)
            for provider in sorted(tts_runtime_providers())
        },
    }


@router.put("/config")
async def save_tts_config(
    req: Request,
    request: TTSConfigRequest,
    product_id: str | None = None,
):
    current = config_manager.get_config(product_id)
    update_data = request.model_dump(exclude_none=True)

    for key, value in update_data.items():
        setattr(current, key, value)

    from packages.pipeline_services.tts_provider import resolve_tts_provider_name

    # Compatibility for pre-provider clients: normalize a model-only update at
    # the API boundary.  New clients send both fields; an explicit mismatch is
    # never rewritten and is rejected below.
    if "model" in update_data and "provider" not in update_data:
        inferred_provider = tts_provider_for_model(str(current.model or ""))
        if inferred_provider:
            current.provider = inferred_provider
    # Retired model alias migration: same rewrite that runs at config-load time
    # in config_reader._migrate_legacy_tts_section.  Without it, the strict
    # voice validation below would 422 legacy clients.
    if current.model == "mimo-v2-tts":
        current.provider = "qwen"
        current.model = "qwen3-tts-flash"
        current.voice = "Rocky"
    try:
        resolve_tts_provider_name(current)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    validate_voice_for_model(current.model, current.voice)

    config_manager.save_config(current, product_id)

    # 即使 product_id 未传，也同步写入 active_product 的 product-level tts：
    # 读取路径（ConfigReader.get_tts_config）按 active_product 优先合 product-level，
    # 写入不同步会让测试与"看似全局实则失效"的客户端读到陈旧 tts。
    if product_id is None:
        active_id = req.app.state.config_reader.active_product_id
        if active_id:
            try:
                config_manager._save_product_config(current, active_id)
            except ValueError:
                # active product 在文件中不存在 -> 静默跳过，保持 root 写入
                pass

    # 始终 reload，确保后续读取是最新值
    req.app.state.config_reader.reload()

    return {"success": True}


def get_valid_preset_voice_ids(model: str) -> set[str] | None:
    """Return valid preset voice IDs for a model, or None if the model doesn't use preset voices.

    VoiceDesign/VoiceClone sub-models return None (skip validation).
    Unknown models also return None.
    Voice data is sourced from catalog.json preset_voices (#386).
    """
    if not model:
        return None
    provider = tts_provider_for_model(model)
    if provider is None:
        return None
    # VoiceDesign/VoiceClone sub-models have no preset voice concept
    if model in ("mimo-v2.5-tts-voicedesign", "mimo-v2.5-tts-voiceclone"):
        return None

    voices = tts_preset_voices(provider)
    if model == "qwen3-tts-instruct-flash":
        return {v["id"] for v in voices if v["id"] not in _INSTRUCT_UNSUPPORTED_VOICES}
    return {v["id"] for v in voices} if voices else None


def validate_voice_for_model(model: str | None, voice: str | None) -> None:
    """Validate that voice belongs to the model's provider.

    Raises HTTPException(422) with a list of valid preset voices when invalid.
    Skips validation for VoiceDesign/VoiceClone sub-models and unknown models.
    """
    if not voice or not model:
        return
    valid_ids = get_valid_preset_voice_ids(model)
    if valid_ids is None:
        return
    if voice in valid_ids:
        return
    provider = tts_provider_for_model(model) or "unknown"
    sorted_ids = sorted(valid_ids)
    preview = sorted_ids[:12]
    detail = (
        f"音色 '{voice}' 不属于模型 {model} ({provider} provider)。"
        f"有效音色 ({len(sorted_ids)} 个): {', '.join(preview)}"
        + (" ..." if len(sorted_ids) > 12 else "")
    )
    raise HTTPException(status_code=422, detail=detail)


@router.get("/voices")
async def get_voices(provider: str | None = None, model: str | None = None):
    from packages.provider_config.catalog import (
        tts_preset_voices,
        tts_runtime_providers,
    )

    if model is not None:
        resolved = tts_provider_for_model(model)
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown TTS model: {model}",
            )
        provider = resolved
    elif provider is None:
        provider = str(DEFAULTS["tts"]["provider"])
    elif provider not in tts_runtime_providers():
        raise HTTPException(
            status_code=400, detail=f"Unsupported TTS provider: {provider}"
        )

    voices = tts_preset_voices(provider)
    if provider == "qwen" and model == "qwen3-tts-instruct-flash":
        voices = [v for v in voices if v["id"] not in _INSTRUCT_UNSUPPORTED_VOICES]
    return {"preset_voices": voices}


@router.post("/preview")
async def preview_tts(request: TTSPreviewRequest):
    try:
        from packages.pipeline_services.tts_provider import (
            TTSError,
            create_tts_provider,
        )

        config = config_manager.get_config().with_defaults()

        if request.model:
            config.model = request.model
        if request.voice:
            config.voice = request.voice
        if request.style_prompt:
            config.style_prompt = request.style_prompt
        if request.voice_design_prompt:
            config.voice_design_prompt = request.voice_design_prompt
        # Pass through Qwen-specific fields from the request so
        # preview uses the current page values, not stale saved ones.
        if request.instructions is not None:
            config.instructions = request.instructions
        if request.optimize_instructions is not None:
            config.optimize_instructions = request.optimize_instructions
        if request.language_type is not None:
            config.language_type = request.language_type
        for key in (
            "speed",
            "vol",
            "pitch",
            "emotion",
            "group_id",
            "endpoint",
            "sample_rate",
            "bitrate",
            "channel",
            "extra_headers",
        ):
            value = getattr(request, key)
            if value is not None:
                setattr(config, key, value)

        validate_voice_for_model(config.model, config.voice)

        # Preview must resolve the same voice as formal synthesis — never randomize (#252)
        config.randomize_voice = False

        model = config.model or ""
        provider_name = request.provider
        if provider_name is None and request.model is not None:
            provider_name = tts_provider_for_model(model)
        if provider_name is None:
            provider_name = config.provider
        if provider_name is None:
            provider_name = tts_provider_for_model(model)
        if provider_name is None:
            raise HTTPException(status_code=400, detail=f"不支持的 TTS model: {model}")
        api_key = app_config.get_api_key(provider_name, section="tts")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail=f"未配置 TTS provider ({provider_name}) 的 API Key",
            )
        config.provider = provider_name
        provider = create_tts_provider(config, app_config)

        audio_bytes = provider.synthesize(request.text, config)

        audio_format = config.audio_format or "wav"
        if audio_format == "wav":
            if _is_playable_wav(audio_bytes):
                media_type = "audio/wav"
                filename = "preview.wav"
            else:
                # Qwen multimodal-generation API returns MP3 even when
                # the caller expects WAV — detect the real format instead
                # of failing with a 502.
                detected = detect_audio_format(audio_bytes)
                if detected is None:
                    raise TTSError("TTS returned unrecognised audio data")
                media_type, ext = detected
                filename = f"preview.{ext}"
        elif audio_format == "pcm16":
            media_type = "audio/L16;rate=24000;channels=1"
            filename = "preview.pcm"
        else:
            detected = detect_audio_format(audio_bytes)
            if detected is not None:
                media_type, ext = detected
                filename = f"preview.{ext}"
            else:
                media_type = "audio/wav"
                filename = "preview.wav"

        return Response(
            content=audio_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    except HTTPException:
        raise
    except TTSError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/voice-clone-sample")
async def upload_voice_clone_sample(
    request: Request,
    file: UploadFile = File(...),
    project_id: str | None = None,
):
    """上传 voiceclone 音频样本"""
    # 验证文件格式
    if file.content_type not in ("audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"):
        raise HTTPException(
            status_code=400,
            detail="只支持 mp3 或 wav 格式的音频文件",
        )

    # 读取文件内容
    content = await file.read()

    # 验证文件大小（10MB 限制）
    max_size = 10 * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"文件大小超过 10MB 限制（当前 {len(content) / 1024 / 1024:.2f}MB）",
        )

    # 确定 MIME 类型
    mime_type = (
        "audio/mpeg"
        if file.content_type in ("audio/mpeg", "audio/mp3")
        else "audio/wav"
    )

    # 使用 root_dir 派生 config_dir，确保测试与生产一致
    root_dir: Path = request.app.state.root_dir
    local_config_manager = TTSConfigManager(config_dir=str(root_dir / "config"))

    # 确定保存路径
    if project_id:
        save_dir = Path(local_config_manager.config_dir) / "projects" / project_id
    else:
        save_dir = Path(local_config_manager.config_dir)

    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / "voice_clone_sample.mp3"

    # 保存文件
    with open(save_path, "wb") as f:
        f.write(content)

    # 更新配置
    config = local_config_manager.get_config(product_id=project_id)
    config.voice_clone_sample_path = str(save_path)
    config.voice_clone_mime_type = mime_type
    local_config_manager.save_config(config, product_id=project_id)

    return {
        "success": True,
        "path": str(save_path),
        "mime_type": mime_type,
        "size_bytes": len(content),
    }
