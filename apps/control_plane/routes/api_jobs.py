from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from packages.domain_core.models import AudioSource, CoverTitle, CoverTitleStyle, JobRecord, Language
from packages.file_store.repository import FileStoreRepository
from apps.control_plane.services.music_library import MusicLibrary

router = APIRouter(tags=["api-jobs"])


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
    platforms: list[str]
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


class BatchJobItem(BaseModel):
    name: str = ""
    manual_script: str = ""
    skip_subtitle: bool = False
    audio_source: AudioSource = "tts"
    language: Language = "mandarin"
    cover_title: CoverTitleRequest | None = None
    music_track_path: str = ""
    music_volume: int = 80


class BatchCreateRequest(BaseModel):
    product: str
    platforms: list[str]
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


def _make_job_response(record: JobRecord, display_index: str, platforms: list[str]) -> dict:
    return {
        "job_id": record.job_id,
        "project_id": record.project_id,
        "product": record.product,
        "name": record.name or record.product,
        "platforms": platforms,
        "phase": record.phase,
        "review_status": record.review_status,
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
        "display_index": display_index,
    }


@router.post("/api/projects/{project_id}/jobs")
def create_job(request: Request, project_id: str, payload: CreateJobRequest):
    job_id = f"job_{payload.product}_{uuid4().hex[:8]}"
    dispatcher = request.app.state.dispatcher
    dispatcher.enqueue_demo_job(
        project_id,
        job_id,
        manual_script=payload.manual_script,
        uploaded_audio_path=payload.uploaded_audio_path,
        audio_source=payload.audio_source,
        language=payload.language,
        cover_title=_cover_title_from_request(payload.cover_title).model_dump(),
        music_track_path=payload.music_track_path,
        music_volume=payload.music_volume,
    )
    repo = FileStoreRepository(request.app.state.root_dir)
    record = JobRecord(
        job_id=job_id,
        project_id=project_id,
        product=payload.product,
        name=payload.name or payload.product,
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
    )
    repo.save_job(project_id, record)

    # 计算 display_index：当前已有 job 数 + 1
    existing_jobs = repo.list_jobs(project_id)
    display_index = f"{len(existing_jobs):03d}"

    return _make_job_response(record, display_index, payload.platforms)


@router.post("/api/projects/{project_id}/jobs/batch")
def create_jobs_batch(request: Request, project_id: str, payload: BatchCreateRequest):
    repo = FileStoreRepository(request.app.state.root_dir)
    dispatcher = request.app.state.dispatcher
    existing_count = len(repo.list_jobs(project_id))

    results: list[dict] = []
    for i, item in enumerate(payload.jobs):
        job_id = f"job_{payload.product}_{uuid4().hex[:8]}"
        cover_title = _cover_title_from_request(item.cover_title)
        dispatcher.enqueue_demo_job(
            project_id,
            job_id,
            manual_script=item.manual_script,
            uploaded_audio_path="",
            audio_source=item.audio_source,
            language=item.language,
            cover_title=cover_title.model_dump(),
            music_track_path=item.music_track_path,
            music_volume=item.music_volume,
        )
        record = JobRecord(
            job_id=job_id,
            project_id=project_id,
            product=payload.product,
            name=item.name or payload.product,
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
        )
        repo.save_job(project_id, record)
        display_index = f"{existing_count + i + 1:03d}"
        results.append(_make_job_response(record, display_index, payload.platforms))

    return {
        "product": payload.product,
        "platforms": payload.platforms,
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
    dispatcher = request.app.state.dispatcher
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(project_id, record.model_copy(update={"phase": "queued", "review_status": "none"}))
    dispatcher.enqueue_demo_job(project_id, job_id)
    return {"status": "queued_for_retry", "job_id": job_id}


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
    repo.save_job(project_id, record.model_copy(update={"manual_script": payload.manual_script}))
    return {"status": "updated", "job_id": job_id, "manual_script": payload.manual_script}


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
    repo.save_job(project_id, record.model_copy(update={"uploaded_audio_path": relative_path}))
    
    return {
        "status": "uploaded",
        "job_id": job_id,
        "audio_path": relative_path,
        "size_bytes": len(content),
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


@router.get("/api/music")
def list_music(request: Request):
    lib = MusicLibrary(request.app.state.root_dir)
    return {"tracks": lib.tracks}


class GenerateCoverTitleRequest(BaseModel):
    script_text: str
    product: str = ""
    brand: str = "滋元堂"


@router.post("/api/cover-title/generate")
def generate_cover_title(payload: GenerateCoverTitleRequest):
    from packages.provider_config.app_config import AppConfigManager
    from packages.pipeline_services.script_service.generator import ScriptGenerator

    if not payload.script_text.strip():
        raise HTTPException(status_code=400, detail="script_text is required")
    app_config = AppConfigManager()
    llm_config = app_config.get_llm_config()

    class _Config:
        api_key = app_config.get_llm_api_key()
        base_url = app_config.get_llm_endpoint()
        model = llm_config.get("model", "deepseek-v4-pro")

    gen = ScriptGenerator(_Config())
    result = gen.generate_cover_title(payload.script_text, payload.product, payload.brand)
    return result
