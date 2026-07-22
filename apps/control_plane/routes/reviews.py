import json
import logging
import random
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from packages.domain_core.models import REVIEW_PHASES, next_phase
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.asset_snapshot import (
    AssetValidationError,
    validate_assets,
    write_reviewed_snapshot,
)
from packages.pipeline_services.script_service import generate_script
from packages.provider_config.config_reader import ConfigReader, ConfigResolver
from packages.provider_config.secret_store import SecretStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class ReviewAction(BaseModel):
    review_gate: str
    force: bool = False


class AssetIndexRequest(BaseModel):
    clip_index: int


class SetAssetRequest(BaseModel):
    clip_index: int
    asset_id: str


class EditScriptRequest(BaseModel):
    script_text: str


class RegenerateWithPromptRequest(BaseModel):
    custom_prompt: str


def _find_job_dir(root_dir: Path, project_id: str, job_id: str) -> Path:
    projects_dir = root_dir / "workspace" / "projects"
    if project_id:
        job_dir = projects_dir / project_id / "runtime" / "jobs" / job_id
        if job_dir.exists():
            return job_dir

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        job_dir = project_dir / "runtime" / "jobs" / job_id
        if job_dir.exists():
            return job_dir

    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


def _find_script_file(job_dir: Path) -> Path | None:
    for f in job_dir.glob("*口播文案.txt"):
        return f
    return None


def _find_job_project(repo: FileStoreRepository, job_id: str) -> str | None:
    projects_root = repo.root.joinpath("workspace", "projects")
    if not projects_root.exists():
        return None

    for project_dir in projects_root.iterdir():
        if not project_dir.is_dir():
            continue
        try:
            repo.load_job(project_dir.name, job_id)
            return project_dir.name
        except Exception:
            continue
    return None


def _validate_review_gate(phase: str, review_gate: str) -> None:
    """Raise HTTP 409 if *phase* is not a review gate or *review_gate* mismatches."""
    if phase not in REVIEW_PHASES:
        raise HTTPException(
            status_code=409,
            detail=f"job is not in a review phase (current: {phase})",
        )
    if review_gate != phase:
        raise HTTPException(
            status_code=409,
            detail=f"review gate mismatch: expected {phase}, got {review_gate}",
        )


@router.post("/{job_id}/approve")
def approve_review(job_id: str, payload: ReviewAction, request: Request) -> dict:
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)

    # ── Phase validation ──
    _validate_review_gate(record.phase, payload.review_gate)

    # ── Asset review specific checks ──
    if record.phase == "asset_review":
        root_dir = Path(request.app.state.root_dir)
        job_dir = _find_job_dir(root_dir, project_id, job_id)
        try:
            clips = validate_assets(job_dir, force=payload.force)
            write_reviewed_snapshot(job_dir, clips)
            logger.info(
                f"[Review] 素材审核快照已保存: {job_dir / 'reviewed_assets.json'}"
            )
        except AssetValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message)
        except FileNotFoundError:
            pass  # no clips to validate — proceed normally

    try:
        nxt = next_phase(record.phase)
    except ValueError:
        nxt = "completed"
    repo.save_job(
        project_id,
        record.model_copy(update={"phase": nxt, "review_status": "approved"}),
    )
    repo.append_review_event(
        project_id,
        {"job_id": job_id, "gate": payload.review_gate, "action": "approved"},
    )
    logger.info(f"[Review] 审核通过: job={job_id}, phase={record.phase} → {nxt}")
    return {"status": "approved", "job_id": job_id, "next_phase": nxt}


@router.post("/{job_id}/reject")
def reject_review(job_id: str, payload: ReviewAction, request: Request) -> dict:
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)

    _validate_review_gate(record.phase, payload.review_gate)

    if record.phase == "tts_review":
        reject_target = "tts_generating"
    elif record.phase == "asset_review":
        reject_target = "asset_retrieving"
    elif record.phase == "script_review":
        reject_target = "script_generating"
    elif record.phase == "final_review":
        reject_target = "video_rendering"
    else:
        reject_target = "queued"

    repo.save_job(
        project_id,
        record.model_copy(update={"phase": reject_target, "review_status": "none"}),
    )
    repo.append_review_event(
        project_id,
        {"job_id": job_id, "gate": payload.review_gate, "action": "rejected"},
    )
    logger.info(f"[Review] 打回重做: job={job_id}, target={reject_target}")
    return {"status": "rejected", "job_id": job_id, "next_phase": reject_target}


@router.post("/{job_id}/edit-script")
def edit_script(
    job_id: str,
    payload: EditScriptRequest,
    request: Request,
) -> dict:
    """Manually edit the script text."""
    root_dir = Path(request.app.state.root_dir)
    project_id = request.query_params.get("project_id", "")

    job_dir = _find_job_dir(root_dir, project_id, job_id)
    script_file = _find_script_file(job_dir)

    if not script_file:
        raise HTTPException(status_code=404, detail="Script file not found")

    script_file.write_text(payload.script_text, encoding="utf-8")
    logger.info(f"[Review] 手动编辑脚本: job={job_id}, file={script_file.name}")

    json_file = script_file.with_suffix(".json")
    if json_file.exists():
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            data["video_script"] = payload.script_text
            json_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"[Review] 更新 JSON 文件失败: {e}")

    return {
        "job_id": job_id,
        "status": "edited",
        "script_file": str(script_file),
    }


@router.post("/{job_id}/regenerate-with-prompt")
def regenerate_with_prompt(
    job_id: str,
    payload: RegenerateWithPromptRequest,
    request: Request,
) -> dict:
    """Regenerate script with custom prompt instructions."""
    root_dir = Path(request.app.state.root_dir)
    project_id = request.query_params.get("project_id", "")

    job_dir = _find_job_dir(root_dir, project_id, job_id)

    manifest_path = job_dir / "job_manifest.json"
    product = ""
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            product = manifest.get("product", "")
        except Exception:
            pass

    if not product:
        product = job_dir.parent.parent.name

    logger.info(
        f"[Review] 附带提示词重新生成: job={job_id}, product={product}, prompt={payload.custom_prompt[:50]}..."
    )

    try:
        config_reader = ConfigReader(config_dir=str(root_dir / "config"))
        config_resolver = ConfigResolver(reader=config_reader, secrets=SecretStore())
        result = generate_script(
            product=product,
            output_dir=job_dir,
            language="mandarin",
            brand="",
            custom_prompt=payload.custom_prompt,
            config_resolver=config_resolver,
        )
        logger.info(
            f"[Review] 重新生成成功: job={job_id}, txt={result.get('txt_path')}"
        )
        return {
            "job_id": job_id,
            "status": "regenerated",
            "result": result,
        }
    except Exception as e:
        logger.error(f"[Review] 重新生成失败: job={job_id}, error={e}")
        raise HTTPException(status_code=500, detail=f"Script generation failed: {e}")


class RejectClipRequest(BaseModel):
    clip_index: int


@router.post("/{job_id}/reject-clip")
def reject_clip(job_id: str, payload: RejectClipRequest, request: Request) -> dict:
    root_dir = Path(request.app.state.root_dir)
    project_id = request.query_params.get("project_id", "")

    job_dir = _find_job_dir(root_dir, project_id, job_id)
    clips_path = job_dir / "selected_clips.json"

    if not clips_path.exists():
        raise HTTPException(status_code=404, detail="selected_clips.json not found")

    try:
        clips = json.loads(clips_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read clips: {e}")

    if payload.clip_index < 0 or payload.clip_index >= len(clips):
        raise HTTPException(
            status_code=400, detail=f"Invalid clip index: {payload.clip_index}"
        )

    rejected_clip = clips[payload.clip_index]
    sentence = rejected_clip.get("sentence", "")
    category = rejected_clip.get("category", "")
    rejected_asset_id = rejected_clip.get("asset_id", "")

    logger.info(
        f"[Review] 打回单个素材: job={job_id}, index={payload.clip_index}, sentence={sentence[:30]}..., asset={rejected_asset_id}"
    )

    if not _find_job_project(FileStoreRepository(root_dir), job_id):
        for project_dir in (root_dir / "workspace" / "projects").iterdir():
            if not project_dir.is_dir():
                continue
            if (project_dir / "runtime" / "jobs" / job_id).exists():
                project_id = project_dir.name
                break

    if not project_id:
        raise HTTPException(status_code=404, detail="project not found for job")

    product = ""
    control_jobs_dir = (
        root_dir / "workspace" / "projects" / project_id / "control" / "jobs"
    )
    job_json_path = control_jobs_dir / f"{job_id}.json"
    if job_json_path.exists():
        job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
        product = job_data.get("product", "")

    try:
        from packages.pipeline_services.asset_library import (
            AssetRepository,
            AssetRetriever,
        )

        db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
        repo = AssetRepository(db_path)
        _ = AssetRetriever(repo)

        candidates = repo.query_by_category(product, category)
        candidates = [
            c
            for c in candidates
            if c.asset_id != rejected_asset_id and c.usage_count < 2
        ]
        if candidates:
            chosen = random.choice(candidates)
            clips[payload.clip_index] = {
                "sentence": sentence,
                "category": category,
                "file_path": chosen.file_path,
                "asset_id": chosen.asset_id,
                "method": "rejected_replaced",
            }
            repo.decrement_usage(rejected_asset_id)
            repo.increment_usage(chosen.asset_id)
            logger.info(f"[Review] 替换素材: {rejected_asset_id} → {chosen.asset_id}")
        else:
            clips[payload.clip_index]["method"] = "rejected_no_alternative"
            logger.warning(
                f"[Review] 无替代素材: sentence={sentence[:30]}..., category={category}"
            )

        clips_path.write_text(
            json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    except Exception as e:
        logger.error(f"[Review] 替换素材失败: {e}")
        clips[payload.clip_index]["method"] = "rejected_error"
        clips_path.write_text(
            json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return {
        "status": "clip_rejected",
        "job_id": job_id,
        "clip_index": payload.clip_index,
        "sentence": sentence,
    }


# ---------------------------------------------------------------------------
# Asset review shared helpers
# ---------------------------------------------------------------------------


def _resolve_job_context(request: Request, job_id: str) -> tuple[Path, str, Path]:
    """Resolve root_dir, project_id, job_dir from request and job_id."""
    root_dir = Path(request.app.state.root_dir)
    project_id = request.query_params.get("project_id", "")
    job_dir = _find_job_dir(root_dir, project_id, job_id)
    return root_dir, project_id, job_dir


def _load_clips(job_dir: Path, clip_index: int) -> list[dict]:
    """Load selected_clips.json and validate clip_index. Raises HTTPException on error."""
    clips_path = job_dir / "selected_clips.json"
    if not clips_path.exists():
        raise HTTPException(status_code=404, detail="selected_clips.json not found")
    try:
        clips = json.loads(clips_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read clips: {e}")
    if clip_index < 0 or clip_index >= len(clips):
        raise HTTPException(status_code=400, detail=f"Invalid clip index: {clip_index}")
    return clips


def _save_clips(job_dir: Path, clips: list[dict]) -> None:
    """Write clips back to selected_clips.json."""
    clips_path = job_dir / "selected_clips.json"
    clips_path.write_text(
        json.dumps(clips, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Asset review: clip / blank / unresolved endpoints (#178)
# ---------------------------------------------------------------------------


def _check_asset_review_phase(root_dir: Path, job_id: str) -> None:
    """Raise 409 if the job is not in the asset_review phase."""
    repo = FileStoreRepository(root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    if record.phase != "asset_review":
        raise HTTPException(
            status_code=409,
            detail=f"asset mutations are only allowed during asset_review phase (current: {record.phase})",
        )


def _ensure_original(clips: list[dict], index: int) -> None:
    """Store the original state of a clip entry before user modification."""
    entry = clips[index]
    if "_original" not in entry:
        entry["_original"] = {
            "sentence": entry.get("sentence", ""),
            "category": entry.get("category", ""),
            "file_path": entry.get("file_path", ""),
            "asset_id": entry.get("asset_id", ""),
            "duration_seconds": entry.get("duration_seconds", 0.0),
            "method": entry.get("method", ""),
            "visual_type": entry.get("visual_type", "unresolved"),
        }


@router.post("/{job_id}/asset/set-blank")
def asset_set_blank(job_id: str, payload: AssetIndexRequest, request: Request) -> dict:
    """Set a clip position to blank (black frame, no asset)."""
    root_dir, _, job_dir = _resolve_job_context(request, job_id)
    _check_asset_review_phase(root_dir, job_id)
    clips = _load_clips(job_dir, payload.clip_index)

    _ensure_original(clips, payload.clip_index)
    clips[payload.clip_index].update(
        {
            "file_path": "",
            "asset_id": "",
            "duration_seconds": 0.0,
            "method": "blank",
            "visual_type": "blank",
        }
    )
    _save_clips(job_dir, clips)
    logger.info(f"[AssetReview] set-blank: job={job_id}, index={payload.clip_index}")
    return {"status": "set_blank", "job_id": job_id, "clip_index": payload.clip_index}


@router.post("/{job_id}/asset/set-asset")
def asset_set_asset(job_id: str, payload: SetAssetRequest, request: Request) -> dict:
    """Manually assign a specific asset to a clip position."""
    root_dir, _, job_dir = _resolve_job_context(request, job_id)
    _check_asset_review_phase(root_dir, job_id)
    clips = _load_clips(job_dir, payload.clip_index)
    repo = FileStoreRepository(root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    product = repo.load_job(project_id, job_id).product

    from packages.pipeline_services.asset_library import AssetRepository

    asset_db = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    asset_db.parent.mkdir(parents=True, exist_ok=True)
    asset_repo = AssetRepository(asset_db)
    asset = asset_repo.query_one(payload.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if asset.status != "available":
        raise HTTPException(status_code=409, detail="asset is not available")
    if asset.product != product:
        raise HTTPException(status_code=409, detail="asset is outside the job product")

    _ensure_original(clips, payload.clip_index)
    clips[payload.clip_index].update(
        {
            "file_path": asset.file_path,
            "asset_id": asset.asset_id,
            "duration_seconds": asset.duration_seconds,
            "category": asset.category,
            "method": "manual",
            "visual_type": "clip",
        }
    )
    _save_clips(job_dir, clips)
    logger.info(
        f"[AssetReview] set-asset: job={job_id}, index={payload.clip_index}, asset={payload.asset_id}"
    )
    return {
        "status": "set_asset",
        "job_id": job_id,
        "clip_index": payload.clip_index,
        "visual_type": "clip",
    }


@router.post("/{job_id}/asset/re-search")
def asset_re_search(job_id: str, payload: AssetIndexRequest, request: Request) -> dict:
    """Re-search for an asset at a clip position.

    Does NOT overwrite clips that are explicitly blank.
    """
    root_dir, _, job_dir = _resolve_job_context(request, job_id)
    _check_asset_review_phase(root_dir, job_id)
    clips = _load_clips(job_dir, payload.clip_index)

    entry = clips[payload.clip_index]
    if entry.get("visual_type") == "blank":
        logger.info(
            f"[AssetReview] re-search skipped for blank: job={job_id}, index={payload.clip_index}"
        )
        return {
            "status": "re_searched",
            "job_id": job_id,
            "clip_index": payload.clip_index,
            "visual_type": "blank",
            "note": "blank clip unchanged by re-search",
        }

    category = entry.get("category", "")

    try:
        from packages.pipeline_services.asset_library import AssetRepository

        db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
        arepo = AssetRepository(db_path)

        candidates = (
            arepo.query_by_category_name(entry.get("product", ""), category or "")
            if category
            else []
        )
        candidates = [c for c in candidates if c.usage_count < 2]
        if candidates:
            chosen = random.choice(candidates)
            _ensure_original(clips, payload.clip_index)
            clips[payload.clip_index].update(
                {
                    "file_path": chosen.file_path,
                    "asset_id": chosen.asset_id,
                    "duration_seconds": chosen.duration_seconds,
                    "visual_type": "clip",
                    "method": "re_search",
                }
            )
            logger.info(
                f"[AssetReview] re-search: job={job_id}, index={payload.clip_index}, asset={chosen.asset_id}"
            )
        else:
            clips[payload.clip_index].update(
                {
                    "file_path": "",
                    "asset_id": "",
                    "visual_type": "unresolved",
                    "method": "re_search_no_result",
                }
            )
            logger.info(
                f"[AssetReview] re-search no result: job={job_id}, index={payload.clip_index}"
            )
    except Exception as e:
        logger.error(f"[AssetReview] re-search failed: {e}")
        clips[payload.clip_index]["visual_type"] = "unresolved"

    _save_clips(job_dir, clips)
    return {
        "status": "re_searched",
        "job_id": job_id,
        "clip_index": payload.clip_index,
        "visual_type": clips[payload.clip_index].get("visual_type"),
    }


@router.post("/{job_id}/asset/restore")
def asset_restore(job_id: str, payload: AssetIndexRequest, request: Request) -> dict:
    """Restore a clip position to its original asset suggestion."""
    root_dir, _, job_dir = _resolve_job_context(request, job_id)
    _check_asset_review_phase(root_dir, job_id)
    clips = _load_clips(job_dir, payload.clip_index)

    entry = clips[payload.clip_index]
    if "_original" not in entry:
        raise HTTPException(status_code=400, detail="no original state to restore")

    original = entry.pop("_original")
    clips[payload.clip_index].update(original)
    _save_clips(job_dir, clips)
    logger.info(f"[AssetReview] restore: job={job_id}, index={payload.clip_index}")
    return {
        "status": "restored",
        "job_id": job_id,
        "clip_index": payload.clip_index,
        "visual_type": original.get("visual_type"),
    }
