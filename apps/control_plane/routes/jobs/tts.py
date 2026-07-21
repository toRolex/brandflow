from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from apps.control_plane.routes.jobs.helpers import (
    _TTS_VOICE_CHANGE_CLEANUP_FILES,
    _find_job_project,
    _first_sentence,
    _INVALIDATE_ARTIFACT_KINDS,
    _resolve_tts_preview_config,
    _resolve_tts_voice_info,
)
from apps.control_plane.routes.jobs.models import UpdateTTSVoiceRequest
from apps.control_plane.routes.tts import validate_voice_for_model
from packages.file_store.repository import FileStoreRepository

router = APIRouter(tags=["api-jobs"])


@router.get("/jobs/{job_id}/tts/voice")
def get_job_tts_voice(job_id: str, request: Request):
    """Return the effective TTS model/voice and which config level it came from."""
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    config_reader = request.app.state.config_reader
    return _resolve_tts_voice_info(record, config_reader)


@router.post("/jobs/{job_id}/tts/preview")
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
    config_reader = request.app.state.config_reader

    # Discover script text: runtime file first, then manual_script on record
    script_text = ""
    job_dir = (
        root_dir / "workspace" / "projects" / project_id / "runtime" / "jobs" / job_id
    )
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


@router.put("/jobs/{job_id}/tts/voice")
def update_job_tts_voice(job_id: str, payload: UpdateTTSVoiceRequest, request: Request):
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
        root_dir
        / "workspace"
        / "projects"
        / project_id
        / "runtime"
        / "jobs"
        / job_id
        / "audio.mp3"
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

    config_reader = request.app.state.config_reader

    if not updates:
        # Nothing changed; return current state
        return _resolve_tts_voice_info(record, config_reader)

    # Validate model+voice atomicity (#252)
    effective_model = updates.get("tts_model", record.tts_model)
    effective_voice = updates.get("tts_voice", record.tts_voice)
    # If model is still empty after update, resolve from config for validation
    if not effective_model:
        product_tts = (
            config_reader.get_tts_config(product_id=record.product)
            if record.product
            else {}
        )
        global_tts = config_reader.get_tts_config()
        effective_model = str(
            product_tts.get("model", "") or global_tts.get("model", "")
        )
    if not effective_voice:
        product_tts = (
            config_reader.get_tts_config(product_id=record.product)
            if record.product
            else {}
        )
        global_tts = config_reader.get_tts_config()
        effective_voice = str(
            product_tts.get("voice", "") or global_tts.get("voice", "")
        )

    validate_voice_for_model(str(effective_model), str(effective_voice))

    if audio_exists and payload.confirm:
        # Invalidate downstream artifacts (preserve script + asset selections)
        preserved = [
            a for a in record.artifacts if a.kind not in _INVALIDATE_ARTIFACT_KINDS
        ]
        updates["artifacts"] = preserved
        updates["phase"] = "tts_generating"
        updates["review_status"] = "none"
        updates["failed_phase"] = None

        # Remove audio file so the next tick actually re-runs TTS
        try:
            audio_path.unlink()
        except OSError:
            pass

        # Cascading invalidation: remove all downstream runtime files (#253)
        job_dir = (
            root_dir
            / "workspace"
            / "projects"
            / project_id
            / "runtime"
            / "jobs"
            / job_id
        )
        for filename in _TTS_VOICE_CHANGE_CLEANUP_FILES:
            file_path = job_dir / filename
            try:
                if file_path.exists():
                    file_path.unlink()
            except OSError:
                pass

        # Invalidate export task so a stale ZIP is never downloadable (#253)
        try:
            from packages.pipeline_services.export_task import ExportTaskService

            ExportTaskService(
                job_id=job_id,
                job_dir=job_dir,
                workspace_dir=root_dir / "workspace",
                project_dir=root_dir / "workspace" / "projects" / project_id,
                export_dir=root_dir
                / "workspace"
                / "projects"
                / project_id
                / "runtime"
                / "exports",
            ).mark_stale()
        except Exception:  # noqa: BLE001 — never block voice change on export cleanup
            pass

    record = record.model_copy(update=updates)  # type: ignore[arg-type]
    repo.save_job(project_id, record)

    config_reader = request.app.state.config_reader
    return _resolve_tts_voice_info(record, config_reader)
