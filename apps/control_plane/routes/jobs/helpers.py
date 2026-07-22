from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from packages.domain_core.models import ExecutionFailure, JobRecord, ProductionMode
from packages.file_store.repository import FileStoreRepository
from packages.provider_config.config_constants import DEFAULTS
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore


def _resolve_product_from_config(root_dir: Path | str) -> tuple[str, str]:
    """从 active product config 读取产品名称和品牌."""
    reader = ConfigReader(config_dir=str(Path(root_dir) / "config"))
    active_id = reader.active_product_id
    cfg = (
        reader.get_product_config(product_id=active_id)
        if active_id
        else reader.get_product_config()
    )
    default_name = cfg.get("default_name", "")
    if not default_name:
        return "", ""
    return default_name, cfg.get("default_brand", "")


def _validate_import_scene_folders(
    root_dir: Path,
    product: str,
    mode: ProductionMode,
    scene_folder_ids: list[str],
) -> ExecutionFailure | None:
    """Validate scene folder selection for import-mode jobs.

    Returns an ``ExecutionFailure`` when selection is empty, a folder is not
    configured, the folder path does not exist on disk, or it contains no
    supported video files. The message includes the specific folder names.
    """
    if mode != "import":
        return None
    config_reader = ConfigReader(config_dir=str(root_dir / "config"))
    scene_config = config_reader.get_scene_config(product_id=product)

    if not scene_folder_ids:
        has_configured_folders = any(
            entry.get("path", "") for entry in scene_config.get("folders", [])
        )
        if has_configured_folders:
            return None  # tick() will populate from scene config (#276)
        return ExecutionFailure(
            code="SCENE_INPUT_MISSING",
            message="请选择至少一个场景文件夹",
            retryable=False,
        )

    configured: dict[str, str] = {
        entry.get("path", ""): entry.get("name", entry.get("path", ""))
        for entry in scene_config.get("folders", [])
        if entry.get("path")
    }

    not_configured: list[str] = []
    not_found: list[str] = []
    no_videos: list[str] = []
    video_ext = {".mp4", ".mov", ".avi"}

    for folder_id in scene_folder_ids:
        if folder_id not in configured:
            not_configured.append(folder_id)
            continue
        folder_path = root_dir / "workspace" / folder_id
        if not folder_path.exists():
            not_found.append(configured[folder_id])
            continue
        has_video = any(
            f.is_file() and f.suffix.lower() in video_ext for f in folder_path.iterdir()
        )
        if not has_video:
            no_videos.append(configured[folder_id])

    if not_configured:
        return ExecutionFailure(
            code="SCENE_FOLDER_NOT_CONFIGURED",
            message=f"未配置的场景文件夹: {', '.join(not_configured)}",
            retryable=False,
        )
    if not_found:
        return ExecutionFailure(
            code="SCENE_FOLDER_NOT_FOUND",
            message=f"场景文件夹不存在: {', '.join(not_found)}",
            retryable=False,
        )
    if no_videos:
        return ExecutionFailure(
            code="SCENE_MEDIA_MISSING",
            message=f"以下场景文件夹没有受支持的视频: {', '.join(no_videos)}",
            retryable=False,
        )
    return None


def _make_job_response(
    record: JobRecord, display_index: str, platforms: list[str]
) -> dict:
    return {
        "job_id": record.job_id,
        "project_id": record.project_id,
        "product": record.product,
        "brand": record.brand,
        "name": record.name or record.product,
        "mode": record.mode,
        "platforms": platforms,
        "phase": record.phase,
        "failed_phase": record.failed_phase,
        "review_status": record.review_status,
        "execution": record.execution.model_dump(),
        "artifacts": [a.model_dump() for a in record.artifacts],
        "manual_script": record.manual_script,
        "uploaded_audio_path": record.uploaded_audio_path,
        "audio_source": record.audio_source,
        "skip_subtitle": record.skip_subtitle,
        "auto_approve": record.auto_approve,
        "language": record.language,
        "cover_title": record.cover_title.model_dump(),
        "music_track_path": record.music_track_path,
        "music_volume": record.music_volume,
        "tts_model": record.tts_model,
        "tts_voice": record.tts_voice,
        "display_index": display_index,
        "scene_folder_ids": record.scene_folder_ids,
    }


def _find_job_project(repo: FileStoreRepository, job_id: str) -> str | None:
    projects_root = repo.root / "workspace" / "projects"
    if not projects_root.exists():
        return None
    for project_dir in projects_root.iterdir():
        if project_dir.is_dir():
            try:
                repo.load_job(project_dir.name, job_id)
                return project_dir.name
            except Exception:
                continue
    return None


def _export_service(request: Request, project_id: str, job_id: str):
    """Build an ExportTaskService bound to this job's on-disk directories."""
    from packages.pipeline_services.export_task import ExportTaskService

    root_dir: Path = request.app.state.root_dir
    workspace_dir = root_dir / "workspace"
    project_dir = workspace_dir / "projects" / project_id
    return ExportTaskService(
        job_id=job_id,
        job_dir=project_dir / "runtime" / "jobs" / job_id,
        workspace_dir=workspace_dir,
        project_dir=project_dir,
        export_dir=project_dir / "runtime" / "exports",
    )


def _read_final_timeline_fingerprint(
    request: Request, project_id: str, job_id: str
) -> str | None:
    root_dir: Path = request.app.state.root_dir
    ft = (
        root_dir
        / "workspace"
        / "projects"
        / project_id
        / "runtime"
        / "jobs"
        / job_id
        / "final_timeline.json"
    )
    if not ft.exists():
        return None
    try:
        return json.loads(ft.read_text(encoding="utf-8")).get("fingerprint")
    except Exception:
        return None


def _run_export_task(service: Any, task_id: str) -> None:
    service.run(task_id)


def _resolve_tts_voice_info(record: JobRecord, config_reader: ConfigReader) -> dict:
    """Resolve effective model/voice and which level it came from.

    Priority: Job-level > Product-level > Global-level.
    """
    product_tts = (
        config_reader.get_tts_config(product_id=record.product)
        if record.product
        else {}
    )
    global_tts = config_reader.get_tts_config()

    effective_model = (
        record.tts_model or product_tts.get("model", "") or global_tts.get("model", "")
    )
    effective_voice = (
        record.tts_voice or product_tts.get("voice", "") or global_tts.get("voice", "")
    )

    # Determine source level
    if record.tts_model or record.tts_voice:
        resolved_from = "job"
    elif record.product and product_tts:
        p_model = product_tts.get("model", "")
        p_voice = product_tts.get("voice", "")
        g_model = global_tts.get("model", "")
        g_voice = global_tts.get("voice", "")
        if p_model != g_model or p_voice != g_voice:
            resolved_from = "product"
        else:
            resolved_from = "global"
    else:
        resolved_from = "global"

    return {
        "model": effective_model,
        "voice": effective_voice,
        "resolved_from": resolved_from,
        "product": record.product,
    }


def _validate_tts_model_voice(
    tts_model: str,
    tts_voice: str,
    product: str,
    config_reader: ConfigReader,
) -> ExecutionFailure | None:
    """Validate a TTS model/voice combination at job creation time.

    Resolves effective model/voice using the same priority as runtime
    (job-level > product-level > global-level) and reuses the validator
    from the TTS config/preview routes. Returns ``ExecutionFailure`` when the
    combination is invalid, or ``None`` when validation is skipped (no override
    provided, or defaults unavailable).
    """
    if not tts_model and not tts_voice:
        return None

    resolved = _resolve_tts_voice_info(
        JobRecord(
            job_id="",
            project_id="",
            product=product,
            phase="queued",
            review_status="none",
            tts_model=tts_model,
            tts_voice=tts_voice,
        ),
        config_reader,
    )
    effective_model = resolved.get("model", "")
    effective_voice = resolved.get("voice", "")
    if not effective_model or not effective_voice:
        return None

    from apps.control_plane.routes.tts import validate_voice_for_model

    try:
        validate_voice_for_model(effective_model, effective_voice)
    except HTTPException as exc:
        message = str(exc.detail) if exc.detail else "TTS 模型/音色组合无效"
        return ExecutionFailure(
            code="TTS_VOICE_MODEL_MISMATCH",
            message=message,
            retryable=False,
        )
    return None


def _first_sentence(text: str) -> str:
    """Extract the first sentence from *text* using Chinese/English punctuation."""
    if not text.strip():
        return ""
    parts = re.split(r"[。！？!?\n]", text)
    for part in parts:
        stripped = part.strip()
        if stripped:
            return stripped
    return text.strip()


_SENTENCE_END_PUNCT = frozenset({"。", "！", "？", "!", "?", "\n"})


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences using Chinese/English punctuation.

    Each sentence includes its trailing punctuation (except newlines).
    """
    if not text or not text.strip():
        return []
    result: list[str] = []
    current: list[str] = []
    for ch in text:
        current.append(ch)
        if ch in _SENTENCE_END_PUNCT:
            sentence = "".join(current).strip()
            if sentence:
                result.append(sentence)
            current = []
    remaining = "".join(current).strip()
    if remaining:
        result.append(remaining)
    return result


def _resolve_tts_preview_config(
    record: JobRecord,
    config_reader: ConfigReader,
    secret_store: SecretStore,
):
    """Resolve TTS config and build provider for preview."""
    tts_cfg = {**config_reader.get_tts_config(product_id=record.product or None)}
    if record.tts_model:
        tts_cfg["model"] = record.tts_model
    if record.tts_voice:
        tts_cfg["voice"] = record.tts_voice

    # Preview must resolve the same voice as formal synthesis — never randomize (#252)
    tts_cfg["randomize_voice"] = False

    from packages.pipeline_services.tts_provider import (
        MiMoTTSProvider,
        QwenTTSProvider,
        TTSConfigShim,
    )

    tts_model: str = str(tts_cfg.get("model", DEFAULTS["tts"]["model"]) or "")
    if tts_model.startswith("qwen"):
        provider = QwenTTSProvider(
            api_key=secret_store.get_api_key("qwen"),
            base_url=secret_store.get_api_base_url("qwen")
            or "https://dashscope.aliyuncs.com/api/v1",
        )
    else:
        provider = MiMoTTSProvider(
            api_key=secret_store.get_api_key("mimo"),
        )
    return provider, TTSConfigShim(tts_cfg)


_INVALIDATE_ARTIFACT_KINDS: frozenset[str] = frozenset(
    {"tts_audio", "sentence_timings", "subtitle", "video_base", "final_video"}
)

_TTS_VOICE_CHANGE_CLEANUP_FILES: tuple[str, ...] = (
    "sentences.json",
    "subtitles.srt",
    "subtitles_offset.srt",
    "audio_aligned.mp3",
    "base.mp4",
    "final.mp4",
    "final_timeline.json",
)

_COVER_TITLE_RATE_LIMIT: dict[str, float] = {}
_COVER_TITLE_COOLDOWN = 3.0  # seconds
