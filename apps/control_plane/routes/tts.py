from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pathlib import Path
from pydantic import BaseModel

from packages.provider_config.secret_store import SecretStore
from packages.provider_config.tts_config import TTSConfigManager

router = APIRouter(prefix="/api/tts", tags=["tts"])

_secret_store = SecretStore()
app_config = _secret_store  # backward compatibility alias
config_manager = TTSConfigManager()


class TTSConfigRequest(BaseModel):
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


class TTSConfigResponse(BaseModel):
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


class TTSPreviewRequest(BaseModel):
    text: str
    model: str = "mimo-v2.5-tts"
    voice: str | None = None
    style_prompt: str | None = None
    voice_design_prompt: str | None = None
    # Qwen-TTS fields
    instructions: str | None = None
    optimize_instructions: bool | None = None
    language_type: str | None = None


PRESET_VOICES = [
    {
        "id": "mimo_default",
        "label": "MiMo 默认音色",
        "note": "官方默认音色，中国区通常映射为冰糖",
        "model": "mimo-v2.5-tts",
    },
    {
        "id": "冰糖",
        "label": "冰糖",
        "note": "中文女声，清亮自然",
        "model": "mimo-v2.5-tts",
    },
    {
        "id": "茉莉",
        "label": "茉莉",
        "note": "中文女声，柔和亲切",
        "model": "mimo-v2.5-tts",
    },
    {
        "id": "苏打",
        "label": "苏打",
        "note": "中文男声，适合短视频口播",
        "model": "mimo-v2.5-tts",
    },
    {
        "id": "白桦",
        "label": "白桦",
        "note": "中文男声，稳重讲解",
        "model": "mimo-v2.5-tts",
    },
    {"id": "Mia", "label": "Mia", "note": "英文女声", "model": "mimo-v2.5-tts"},
    {"id": "Chloe", "label": "Chloe", "note": "英文女声", "model": "mimo-v2.5-tts"},
    {"id": "Milo", "label": "Milo", "note": "英文男声", "model": "mimo-v2.5-tts"},
    {"id": "Dean", "label": "Dean", "note": "英文男声", "model": "mimo-v2.5-tts"},
]

QWEN_VOICES = [
    {
        "id": "Rocky",
        "label": "阿强（粤语）",
        "note": "幽默风趣的粤语男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Kiki",
        "label": "阿清（粤语）",
        "note": "甜美的港妹闺蜜女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Cherry",
        "label": "芊悦",
        "note": "阳光积极、亲切自然女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Serena",
        "label": "苏瑶",
        "note": "温柔女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Ethan",
        "label": "晨煦",
        "note": "阳光温暖男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Chelsie",
        "label": "千雪",
        "note": "二次元虚拟女友声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Momo",
        "label": "茉兔",
        "note": "撒娇搞怪女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Vivian",
        "label": "十三",
        "note": "拽拽可爱的女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Moon",
        "label": "月白",
        "note": "率性帅气男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Maia",
        "label": "四月",
        "note": "知性温柔女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Kai",
        "label": "凯",
        "note": "磁性男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Nofish",
        "label": "不吃鱼",
        "note": "设计师男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Bella",
        "label": "萌宝",
        "note": "小萝莉女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Jennifer",
        "label": "詹妮弗",
        "note": "电影质感美语女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Ryan",
        "label": "甜茶",
        "note": "节奏感强男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Katerina",
        "label": "卡捷琳娜",
        "note": "御姐女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Eldric Sage",
        "label": "沧明子",
        "note": "沉稳睿智老者和声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Mia",
        "label": "乖小妹",
        "note": "温顺乖巧女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Mochi",
        "label": "沙小弥",
        "note": "聪明伶俐童声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Bellona",
        "label": "燕铮莺",
        "note": "洪亮吐字清晰女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Vincent",
        "label": "田叔",
        "note": "沙哑烟嗓男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Bunny",
        "label": "萌小姬",
        "note": "萌属性小萝莉",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Neil",
        "label": "阿闻",
        "note": "专业新闻主持人男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Elias",
        "label": "墨讲师",
        "note": "知识讲解女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Arthur",
        "label": "徐大爷",
        "note": "质朴方言男声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Nini",
        "label": "邻家妹妹",
        "note": "软糯甜美少女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Seren",
        "label": "小婉",
        "note": "温和舒缓女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Pip",
        "label": "顽屁小孩",
        "note": "调皮童真男童声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Stella",
        "label": "少女阿月",
        "note": "甜美少女声",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Jada",
        "label": "阿珍（上海话）",
        "note": "风风火火沪上阿姐",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Dylan",
        "label": "晓东（北京话）",
        "note": "北京胡同少年",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Li",
        "label": "老李（南京话）",
        "note": "耐心瑜伽老师",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Marcus",
        "label": "秦川（陕西话）",
        "note": "面宽话短老陕",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Roy",
        "label": "阿杰（闽南语）",
        "note": "台湾哥仔",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Peter",
        "label": "李彼得（天津话）",
        "note": "天津相声捧哏",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Sunny",
        "label": "晴儿（四川话）",
        "note": "甜心川妹子",
        "model": "qwen3-tts-instruct-flash",
    },
    {
        "id": "Eric",
        "label": "程川（四川话）",
        "note": "成都男声",
        "model": "qwen3-tts-instruct-flash",
    },
]

INSTRUCT_UNSUPPORTED_VOICES = {"Jennifer", "Ryan", "Katerina"}


@router.get("/config", response_model=TTSConfigResponse)
async def get_tts_config(project_id: str | None = None):
    config = config_manager.get_config(project_id)
    return TTSConfigResponse(**config.to_dict())


@router.put("/config")
async def save_tts_config(request: TTSConfigRequest, project_id: str | None = None):
    current = config_manager.get_config(project_id)
    update_data = request.model_dump(exclude_none=True)

    for key, value in update_data.items():
        setattr(current, key, value)

    validate_voice_for_model(current.model, current.voice)

    config_manager.save_config(current, project_id)
    return {"success": True}


MODEL_TO_PROVIDER = {
    "mimo-v2.5-tts": "mimo",
    "mimo-v2.5-tts-voicedesign": "mimo",
    "mimo-v2.5-tts-voiceclone": "mimo",
    "qwen3-tts-flash": "qwen",
    "qwen3-tts-instruct-flash": "qwen",
}


def get_valid_preset_voice_ids(model: str) -> set[str] | None:
    """Return valid preset voice IDs for a model, or None if the model doesn't use preset voices.

    VoiceDesign/VoiceClone sub-models return None (skip validation).
    Unknown models also return None.
    """
    if not model:
        return None
    provider = MODEL_TO_PROVIDER.get(model)
    if provider is None:
        return None
    # VoiceDesign/VoiceClone sub-models have no preset voice concept
    if model in ("mimo-v2.5-tts-voicedesign", "mimo-v2.5-tts-voiceclone"):
        return None
    if provider == "mimo":
        return {v["id"] for v in PRESET_VOICES}
    if provider == "qwen":
        if model == "qwen3-tts-instruct-flash":
            return {
                v["id"]
                for v in QWEN_VOICES
                if v["id"] not in INSTRUCT_UNSUPPORTED_VOICES
            }
        return {v["id"] for v in QWEN_VOICES}
    return None


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
    provider = MODEL_TO_PROVIDER.get(model, "unknown")
    sorted_ids = sorted(valid_ids)
    preview = sorted_ids[:12]
    detail = (
        f"音色 '{voice}' 不属于模型 {model} ({provider} provider)。"
        f"有效音色 ({len(sorted_ids)} 个): {', '.join(preview)}"
        + (" ..." if len(sorted_ids) > 12 else "")
    )
    raise HTTPException(status_code=422, detail=detail)


@router.get("/voices")
async def get_voices(provider: str = "mimo", model: str | None = None):
    if model is not None:
        resolved = MODEL_TO_PROVIDER.get(model)
        if resolved is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown TTS model: {model}",
            )
        provider = resolved
    elif provider not in ("mimo", "qwen"):
        raise HTTPException(
            status_code=400, detail=f"Unsupported TTS provider: {provider}"
        )
    if provider == "qwen":
        voices = QWEN_VOICES
        if model == "qwen3-tts-instruct-flash":
            voices = [v for v in voices if v["id"] not in INSTRUCT_UNSUPPORTED_VOICES]
        return {"preset_voices": voices}
    return {"preset_voices": PRESET_VOICES}


@router.post("/preview")
async def preview_tts(request: TTSPreviewRequest):
    try:
        from packages.pipeline_services.tts_provider import (
            MiMoTTSProvider,
            QwenTTSProvider,
            TTSError,
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

        validate_voice_for_model(config.model, config.voice)

        model = config.model or ""
        if model.startswith("qwen"):
            api_key = app_config.get_api_key("qwen")
            if not api_key:
                raise HTTPException(status_code=500, detail="未配置 DASHSCOPE_API_KEY")
            base_url = (
                app_config.get_api_base_url("qwen")
                or "https://dashscope.aliyuncs.com/api/v1"
            )
            provider = QwenTTSProvider(api_key=api_key, base_url=base_url)
        elif model.startswith("mimo"):
            api_key = app_config.get_api_key("mimo")
            if not api_key:
                raise HTTPException(status_code=500, detail="未配置 MIMO_API_KEY")
            provider = MiMoTTSProvider(api_key=api_key)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的 TTS model: {model}")

        audio_bytes = provider.synthesize(request.text, config)

        audio_format = config.audio_format or "wav"
        if audio_format == "wav":
            if not (
                len(audio_bytes) >= 12
                and audio_bytes[:4] == b"RIFF"
                and audio_bytes[8:12] == b"WAVE"
            ):
                raise TTSError("TTS returned invalid WAV audio")
            media_type = "audio/wav"
            filename = "preview.wav"
        elif audio_format == "pcm16":
            media_type = "audio/L16;rate=24000;channels=1"
            filename = "preview.pcm"
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
    config = local_config_manager.get_config(project_id)
    config.voice_clone_sample_path = str(save_path)
    config.voice_clone_mime_type = mime_type
    local_config_manager.save_config(config, project_id)

    return {
        "success": True,
        "path": str(save_path),
        "mime_type": mime_type,
        "size_bytes": len(content),
    }
