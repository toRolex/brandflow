from __future__ import annotations

import json
import re
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from packages.domain_core.models import (
    AudioSource,
    CoverTitle,
    CoverTitleStyle,
    ExecutionFailure,
    JobRecord,
    Language,
    PhaseExecutionState,
    ProductionMode,
)
from packages.file_store.repository import FileStoreRepository
from packages.provider_config.config_reader import ConfigReader
from packages.provider_config.secret_store import SecretStore
from apps.control_plane.services.music_library import MusicLibrary

router = APIRouter(tags=["api-jobs"])


def _resolve_product_defaults(
    product: str, brand: str, root_dir: Path | str
) -> tuple[str, str]:
    """当 product/brand 同时为空时从 product config 读取默认值."""
    if product.strip():
        return product, brand
    reader = ConfigReader(config_dir=str(Path(root_dir) / "config"))
    active_id = reader.active_product_id
    cfg = (
        reader.get_product_config(product_id=active_id)
        if active_id
        else reader.get_product_config()
    )
    default_name = cfg.get("default_name", "")
    if not default_name:
        return product, brand
    return default_name, cfg.get("default_brand", brand)


def _validate_import_scene_folders(
    root_dir: Path,
    product: str,
    mode: ProductionMode,
    scene_folder_ids: list[str],
) -> "ExecutionFailure | None":
    """Validate scene folder selection for import-mode jobs.

    Returns an ``ExecutionFailure`` when selection is empty, a folder is not
    configured, the folder path does not exist on disk, or it contains no
    supported video files. The message includes the specific folder names.
    """
    if mode != "import":
        return None
    if not scene_folder_ids:
        return ExecutionFailure(
            code="SCENE_INPUT_MISSING",
            message="请选择至少一个场景文件夹",
            retryable=False,
        )

    config_reader = ConfigReader(config_dir=str(root_dir / "config"))
    scene_config = config_reader.get_scene_config(product_id=product)
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


class CoverTitleStyleRequest(BaseModel):
    primary_color: str = "#FFD700"
    outline_color: str = "#000000"
    highlight_color: str = "#FF0000"
    outline_width: float = 2.0
    position: str = "center"


class CoverTitleRequest(BaseModel):
    text: str = ""
    highlight_words: list[str] = []
    style: CoverTitleStyleRequest | None = None


class CreateJobRequest(BaseModel):
    product: str
    brand: str = ""
    platforms: list[str]
    mode: ProductionMode = "generate"
    asset: str | None = None
    manual_script: str = ""
    uploaded_audio_path: str = ""
    name: str = ""
    skip_subtitle: bool = False
    auto_approve: bool = False
    audio_source: AudioSource = "tts"
    language: Language = "mandarin"
    cover_title: CoverTitleRequest | None = None
    music_track_path: str = ""
    music_volume: int = 80
    tts_model: str = ""
    tts_voice: str = ""
    scene_folder_ids: list[str] = []


class BatchJobItem(BaseModel):
    name: str = ""
    manual_script: str = ""
    mode: ProductionMode = "generate"
    skip_subtitle: bool = False
    audio_source: AudioSource = "tts"
    language: Language = "mandarin"
    cover_title: CoverTitleRequest | None = None
    music_track_path: str = ""
    music_volume: int = 80
    tts_model: str = ""
    tts_voice: str = ""
    scene_folder_ids: list[str] = []


class BatchCreateRequest(BaseModel):
    product: str
    brand: str = ""
    platforms: list[str]
    mode: ProductionMode = "generate"
    auto_approve: bool = False
    jobs: list[BatchJobItem]


def _cover_title_from_request(req: CoverTitleRequest | None) -> CoverTitle:
    if req is None:
        return CoverTitle()
    style = CoverTitleStyle()
    if req.style is not None:
        style = CoverTitleStyle(
            primary_color=req.style.primary_color,
            outline_color=req.style.outline_color,
            highlight_color=req.style.highlight_color,
            outline_width=req.style.outline_width,
            position=req.style.position,  # type: ignore[arg-type]
        )
    return CoverTitle(
        text=req.text,
        highlight_words=req.highlight_words,
        style=style,
    )


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


@router.post("/api/projects/{project_id}/jobs")
def create_job(request: Request, project_id: str, payload: CreateJobRequest):
    product, brand = _resolve_product_defaults(
        payload.product, payload.brand, request.app.state.root_dir
    )
    if not product.strip():
        raise HTTPException(status_code=400, detail="product is required")
    validation_error = _validate_import_scene_folders(
        Path(request.app.state.root_dir), product, payload.mode, payload.scene_folder_ids
    )
    if validation_error is not None:
        raise HTTPException(status_code=400, detail=validation_error.model_dump())
    job_id = f"job_{product}_{uuid4().hex[:8]}"
    repo = FileStoreRepository(request.app.state.root_dir)
    record = JobRecord(
        job_id=job_id,
        project_id=project_id,
        product=product,
        brand=brand,
        name=payload.name or product,
        mode=payload.mode,
        phase="queued",
        review_status="none",
        manual_script=payload.manual_script,
        uploaded_audio_path=payload.uploaded_audio_path,
        audio_source=payload.audio_source,
        skip_subtitle=payload.skip_subtitle,
        auto_approve=payload.auto_approve,
        language=payload.language,
        cover_title=_cover_title_from_request(payload.cover_title),
        music_track_path=payload.music_track_path,
        music_volume=payload.music_volume,
        tts_model=payload.tts_model,
        tts_voice=payload.tts_voice,
        scene_folder_ids=payload.scene_folder_ids,
    )
    repo.save_job(project_id, record)

    # 计算 display_index：当前已有 job 数 + 1
    existing_jobs = repo.list_jobs(project_id)
    display_index = f"{len(existing_jobs):03d}"

    return _make_job_response(record, display_index, payload.platforms)


@router.post("/api/projects/{project_id}/jobs/batch")
def create_jobs_batch(request: Request, project_id: str, payload: BatchCreateRequest):
    product, brand = _resolve_product_defaults(
        payload.product, payload.brand, request.app.state.root_dir
    )
    if not product.strip():
        raise HTTPException(status_code=400, detail="product is required")
    repo = FileStoreRepository(request.app.state.root_dir)
    existing_count = len(repo.list_jobs(project_id))

    results: list[dict] = []
    for i, item in enumerate(payload.jobs):
        validation_error = _validate_import_scene_folders(
            Path(request.app.state.root_dir),
            product,
            item.mode,
            item.scene_folder_ids,
        )
        if validation_error is not None:
            raise HTTPException(status_code=400, detail=validation_error.model_dump())
        job_id = f"job_{product}_{uuid4().hex[:8]}"
        cover_title = _cover_title_from_request(item.cover_title)
        record = JobRecord(
            job_id=job_id,
            project_id=project_id,
            product=product,
            brand=brand,
            name=item.name or product,
            mode=item.mode,
            phase="queued",
            review_status="none",
            manual_script=item.manual_script,
            uploaded_audio_path="",
            audio_source=item.audio_source,
            skip_subtitle=item.skip_subtitle,
            auto_approve=payload.auto_approve,
            language=item.language,
            cover_title=cover_title,
            music_track_path=item.music_track_path,
            music_volume=item.music_volume,
            tts_model=item.tts_model,
            tts_voice=item.tts_voice,
            scene_folder_ids=item.scene_folder_ids,
        )
        repo.save_job(project_id, record)
        display_index = f"{existing_count + i + 1:03d}"
        results.append(_make_job_response(record, display_index, payload.platforms))

    return {
        "product": product,
        "platforms": payload.platforms,
        "mode": payload.mode,
        "auto_approve": payload.auto_approve,
        "count": len(results),
        "results": results,
    }


@router.get("/api/jobs/{job_id}")
def get_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    projects_root = repo.root / "workspace" / "projects"
    if projects_root.exists():
        for project_dir in projects_root.iterdir():
            if project_dir.is_dir():
                try:
                    record = repo.load_job(project_dir.name, job_id)
                    job_data = record.model_dump()
                    job_data["project_id"] = project_dir.name
                    return job_data
                except Exception:
                    continue
    raise HTTPException(status_code=404, detail="job not found")


@router.post("/api/jobs/{job_id}/pause")
def pause_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"phase": "paused"}))
    return {"status": "paused", "job_id": job_id}


@router.post("/api/jobs/{job_id}/retry")
def retry_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    if record.phase != "failed":
        raise HTTPException(status_code=409, detail="job has no failed phase to retry")
    if record.failed_phase is None:
        # Legacy failed jobs (no structured failed_phase yet, e.g. generate/
        # worker paths not migrated to the execution contract): keep the old
        # reset-to-queued retry behaviour instead of rejecting them.
        repo.save_job(
            project_id,
            record.model_copy(
                update={
                    "phase": "queued",
                    "review_status": "none",
                    "execution": PhaseExecutionState(
                        max_attempts=record.execution.max_attempts
                    ),
                }
            ),
        )
        return {"status": "queued_for_retry", "job_id": job_id}

    from packages.pipeline_services.phase_orchestrator import PhaseContext

    project_dir = request.app.state.root_dir / "workspace" / "projects" / project_id
    scene_config = request.app.state.config_reader.get_scene_config(
        product_id=record.product
    )
    configured_paths = [
        entry.get("path", "")
        for entry in scene_config.get("folders", [])
        if entry.get("path")
    ]
    scene_folder_paths = (
        record.scene_folder_ids
        if record.mode == "import" and record.scene_folder_ids
        else configured_paths
    )
    ctx = PhaseContext(
        job_id=record.job_id,
        project_dir=project_dir,
        root_dir=request.app.state.root_dir,
        product=record.product,
        brand=record.brand,
        options={
            "manual_script": record.manual_script,
            "uploaded_audio_path": record.uploaded_audio_path,
            "language": record.language,
            "mode": record.mode,
        },
        scene_folder_paths=scene_folder_paths,
        transition_duration_ms=scene_config.get("transition_duration_ms", 500),
        scene_config=scene_config,
    )
    validation_error = request.app.state.orchestrator.validate_phase_input(
        record.failed_phase, ctx
    )
    if validation_error is not None:
        raise HTTPException(status_code=409, detail=validation_error.model_dump())

    repo.save_job(
        project_id,
        record.model_copy(
            update={
                "phase": record.failed_phase,
                "failed_phase": None,
                "review_status": "none",
                "execution": PhaseExecutionState(
                    max_attempts=record.execution.max_attempts
                ),
            }
        ),
    )
    return {"status": "phase_queued_for_retry", "job_id": job_id}


class MigrateScenesRequest(BaseModel):
    scene_folder_ids: list[str]


@router.post("/api/jobs/{job_id}/migrate-scenes")
def migrate_scenes(
    request: Request, job_id: str, payload: MigrateScenesRequest
):
    """Migrate an import job that lacks valid scene input to use new folders.

    Preserves user-level configuration (manual script, TTS/language settings,
    uploaded audio, cover title, music), clears stale artifacts/runtime files,
    validates the new scene folder selection, and resets the job to ``queued``.
    """
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    record = repo.load_job(project_id, job_id)
    if record.phase != "migration_required":
        raise HTTPException(
            status_code=409, detail="job does not require scene migration"
        )

    validation_error = _validate_import_scene_folders(
        Path(request.app.state.root_dir),
        record.product,
        record.mode,
        payload.scene_folder_ids,
    )
    if validation_error is not None:
        raise HTTPException(status_code=400, detail=validation_error.model_dump())

    # Clear runtime artifacts so the job restarts with clean state.
    job_runtime_dir = (
        Path(request.app.state.root_dir)
        / "workspace"
        / "projects"
        / project_id
        / "runtime"
        / "jobs"
        / job_id
    )
    if job_runtime_dir.exists():
        shutil.rmtree(job_runtime_dir)

    reset_record = record.model_copy(
        update={
            "phase": "queued",
            "review_status": "none",
            "failed_phase": None,
            "scene_folder_ids": payload.scene_folder_ids,
            "artifacts": [],
            "execution": PhaseExecutionState(
                max_attempts=record.execution.max_attempts
            ),
        }
    )
    repo.save_job(project_id, reset_record)
    return {
        "status": "migrated",
        "job_id": job_id,
        "phase": "queued",
        "scene_folder_ids": payload.scene_folder_ids,
    }


@router.delete("/api/jobs/{job_id}")
def delete_job(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    repo.delete_job(project_id, job_id)
    return {"status": "deleted", "job_id": job_id}


class RenameJobRequest(BaseModel):
    name: str


@router.put("/api/jobs/{job_id}/rename")
def rename_job(request: Request, job_id: str, payload: RenameJobRequest):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"name": payload.name}))
    return {"job_id": job_id, "name": payload.name}


@router.get("/api/jobs/{job_id}/logs")
def get_job_logs(request: Request, job_id: str):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    return {"logs": record.last_error or "", "job_id": job_id}


class UpdateScriptRequest(BaseModel):
    manual_script: str


@router.post("/api/jobs/{job_id}/script")
def update_manual_script(request: Request, job_id: str, payload: UpdateScriptRequest):
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(
        project_id, record.model_copy(update={"manual_script": payload.manual_script})
    )
    return {
        "status": "updated",
        "job_id": job_id,
        "manual_script": payload.manual_script,
    }


@router.post("/api/jobs/{job_id}/audio")
async def upload_job_audio(request: Request, job_id: str, file: UploadFile):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename required")
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    root_dir: Path = request.app.state.root_dir
    audio_dir = root_dir / "workspace" / "projects" / project_id / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{job_id}_{Path(file.filename).name}"
    dest = audio_dir / safe_name
    content = await file.read()
    dest.write_bytes(content)

    relative_path = f"workspace/projects/{project_id}/audio/{safe_name}"
    record = repo.load_job(project_id, job_id)
    repo.save_job(
        project_id, record.model_copy(update={"uploaded_audio_path": relative_path})
    )

    return {
        "status": "uploaded",
        "job_id": job_id,
        "audio_path": relative_path,
        "size_bytes": len(content),
    }


@router.get("/api/jobs/{job_id}/export")
def export_job(request: Request, job_id: str):
    """Build and download an export bundle ZIP for a completed job."""
    from packages.pipeline_services.export_service import build_export_bundle

    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    record = repo.load_job(project_id, job_id)
    if record.phase != "completed":
        raise HTTPException(status_code=400, detail="job not yet completed")

    root_dir: Path = request.app.state.root_dir
    workspace_dir = root_dir / "workspace"
    project_dir = workspace_dir / "projects" / project_id
    job_dir = project_dir / "runtime" / "jobs" / job_id
    export_dir = project_dir / "runtime" / "exports"

    zip_path = build_export_bundle(
        job_dir=job_dir,
        workspace_dir=workspace_dir,
        project_dir=project_dir,
        export_dir=export_dir,
    )

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=f"export_{job_id}.zip",
    )


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


@router.get("/api/music")
def list_music(request: Request):
    lib = MusicLibrary(request.app.state.root_dir)
    return {"tracks": lib.tracks}


@router.get("/api/scene-folders")
def list_scene_folders(request: Request, product: str = ""):
    """Return configured scene folders for the active or requested product."""
    config_reader = request.app.state.config_reader
    scene_config = config_reader.get_scene_config(product_id=product)
    return {
        "folders": [
            {
                "name": entry.get("name", ""),
                "path": entry.get("path", ""),
            }
            for entry in scene_config.get("folders", [])
            if entry.get("path")
        ]
    }


class GenerateCoverTitleRequest(BaseModel):
    script_text: str
    product: str = ""
    brand: str = ""


_COVER_TITLE_RATE_LIMIT: dict[str, float] = {}
_COVER_TITLE_COOLDOWN = 3.0  # seconds


@router.post("/api/cover-title/generate")
def generate_cover_title(payload: GenerateCoverTitleRequest, request: Request):
    import time
    from packages.pipeline_services.script_service.generator import ScriptGenerator

    if not payload.script_text.strip():
        raise HTTPException(status_code=400, detail="script_text is required")

    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    last = _COVER_TITLE_RATE_LIMIT.get(client_ip, 0)
    if now - last < _COVER_TITLE_COOLDOWN:
        raise HTTPException(
            status_code=429, detail=f"请 {_COVER_TITLE_COOLDOWN} 秒后再试"
        )
    _COVER_TITLE_RATE_LIMIT[client_ip] = now

    config_reader = request.app.state.config_reader
    secret_store = request.app.state.secret_store
    llm_config = config_reader.get_llm_config()

    class _Config:
        api_key = secret_store.get_llm_api_key(config_reader)
        base_url = secret_store.get_llm_endpoint(config_reader)
        model = llm_config.get("model", "deepseek-v4-pro")

    gen = ScriptGenerator(_Config())
    result = gen.generate_cover_title(
        payload.script_text, payload.product, payload.brand
    )
    return result


# ---------------------------------------------------------------------------
# Job-level TTS voice selection, preview, and change (#177)
# ---------------------------------------------------------------------------


class UpdateTTSVoiceRequest(BaseModel):
    model: str | None = None
    voice: str | None = None
    confirm: bool = False


def _resolve_tts_voice_info(
    record: JobRecord, config_reader: ConfigReader
) -> dict:
    """Resolve effective model/voice and which level it came from.

    Priority: Job-level > Product-level > Global-level.
    """
    product_tts = config_reader.get_tts_config(product_id=record.product) if record.product else {}
    global_tts = config_reader.get_tts_config()

    effective_model = record.tts_model or product_tts.get("model", "") or global_tts.get("model", "")
    effective_voice = record.tts_voice or product_tts.get("voice", "") or global_tts.get("voice", "")

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
    }


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
) -> tuple[Any, Any]:
    """Resolve TTS config and build provider for preview."""
    tts_cfg = {**config_reader.get_tts_config(product_id=record.product or None)}
    if record.tts_model:
        tts_cfg["model"] = record.tts_model
    if record.tts_voice:
        tts_cfg["voice"] = record.tts_voice

    from packages.pipeline_services.tts_provider import (
        MiMoTTSProvider,
        QwenTTSProvider,
        TTSConfigShim,
    )

    tts_model = tts_cfg.get("model", "mimo-v2.5-tts") or ""
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


@router.get("/api/jobs/{job_id}/tts/voice")
def get_job_tts_voice(job_id: str, request: Request):
    """Return the effective TTS model/voice and which config level it came from."""
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    config_reader: ConfigReader = request.app.state.config_reader
    return _resolve_tts_voice_info(record, config_reader)


@router.post("/api/jobs/{job_id}/tts/preview")
def preview_job_tts(job_id: str, request: Request):
    """Generate TTS for the first sentence only.

    Does NOT persist audio, modify artifacts, or advance the job phase.
    """
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    record = repo.load_job(project_id, job_id)
    root_dir: Path = request.app.state.root_dir
    config_reader: ConfigReader = request.app.state.config_reader

    # Discover script text: runtime file first, then manual_script on record
    script_text = ""
    job_dir = root_dir / "workspace" / "projects" / project_id / "runtime" / "jobs" / job_id
    for p in job_dir.glob("*口播文案.txt"):
        script_text = p.read_text(encoding="utf-8").strip()
        break
    if not script_text:
        for p in job_dir.glob("*口播文案.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                script_text = data.get("text", "").strip()
                break
            except json.JSONDecodeError:
                pass
    if not script_text:
        script_text = record.manual_script

    if not script_text or not script_text.strip():
        raise HTTPException(status_code=400, detail="job has no script text to preview")

    first = _first_sentence(script_text)
    if not first:
        raise HTTPException(status_code=400, detail="could not extract first sentence")

    provider, shim = _resolve_tts_preview_config(
        record, config_reader, request.app.state.secret_store
    )

    try:
        audio_bytes = provider.synthesize(first, shim)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS preview failed: {e}")

    audio_format = shim.audio_format or "wav"
    if audio_format == "wav":
        media_type = "audio/wav"
    elif audio_format == "pcm16":
        media_type = "audio/L16;rate=24000;channels=1"
    else:
        media_type = "audio/wav"

    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": "attachment; filename=preview.wav",
            "X-Preview-Sentence": first[:80],
        },
    )


_INVALIDATE_ARTIFACT_KINDS: frozenset[str] = frozenset(
    {"tts_audio", "subtitle", "video_base", "final_video"}
)


@router.put("/api/jobs/{job_id}/tts/voice")
def update_job_tts_voice(
    job_id: str, payload: UpdateTTSVoiceRequest, request: Request
):
    """Update job-level TTS model/voice selection.

    When formal TTS audio exists (audio.mp3), the caller must set
    ``confirm=true``.  On confirmation, downstream artifacts (audio,
    subtitles, video, final) are invalidated and the job phase resets to
    ``tts_generating`` so the pipeline re-generates from TTS.
    Script and asset-selection artifacts are preserved.
    """
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")

    record = repo.load_job(project_id, job_id)
    root_dir: Path = request.app.state.root_dir

    # Check for existing formal audio
    audio_path = (
        root_dir / "workspace" / "projects" / project_id
        / "runtime" / "jobs" / job_id / "audio.mp3"
    )
    audio_exists = audio_path.exists()

    if audio_exists and not payload.confirm:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TTS_AUDIO_EXISTS",
                "message": "正式 TTS 音频已存在，更换音色将失效下游产物，请确认",
                "audio_exists": True,
            },
        )

    # Apply voice/model updates
    updates: dict[str, object] = {}
    if payload.model is not None:
        updates["tts_model"] = payload.model
    if payload.voice is not None:
        updates["tts_voice"] = payload.voice

    if not updates:
        # Nothing changed; return current state
        config_reader: ConfigReader = request.app.state.config_reader
        return _resolve_tts_voice_info(record, config_reader)

    if audio_exists and payload.confirm:
        # Invalidate downstream artifacts (preserve script + asset selections)
        preserved = [
            a
            for a in record.artifacts
            if a.kind not in _INVALIDATE_ARTIFACT_KINDS
        ]
        updates["artifacts"] = preserved
        updates["phase"] = "tts_generating"
        updates["review_status"] = "none"

        # Remove audio file so the next tick actually re-runs TTS
        try:
            audio_path.unlink()
        except OSError:
            pass

    record = record.model_copy(update=updates)  # type: ignore[arg-type]
    repo.save_job(project_id, record)

    config_reader = request.app.state.config_reader
    return _resolve_tts_voice_info(record, config_reader)
