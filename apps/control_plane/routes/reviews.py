import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from packages.domain_core.models import REVIEW_PHASES, next_phase
from packages.file_store.repository import FileStoreRepository
from apps.control_plane.routes.jobs.helpers import _resolve_job_project
from packages.file_store.layout import WorkspaceLayout
from packages.log_service.log_writer import log_error
from packages.pipeline_services.asset_snapshot import (
    AssetValidationError,
    validate_assets,
    write_reviewed_snapshot,
)
from packages.pipeline_services.asset_library.replacement import select_replacement
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


def _find_job_dir(layout: WorkspaceLayout, project_id: str, job_id: str) -> Path:
    if project_id:
        job_dir = layout.job_runtime_dir(project_id, job_id)
        if job_dir.exists():
            return job_dir

    for project_dir in layout.projects_dir().iterdir():
        if not project_dir.is_dir():
            continue
        candidate_project_id = project_dir.name
        job_dir = layout.job_runtime_dir(candidate_project_id, job_id)
        if job_dir.exists():
            return job_dir

    raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


def _find_script_file(job_dir: Path) -> Path | None:
    for f in job_dir.glob("*口播文案.txt"):
        return f
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
    project_id = _resolve_job_project(repo, job_id)
    record = repo.load_job(project_id, job_id)

    # ── Phase validation ──
    _validate_review_gate(record.phase, payload.review_gate)

    # ── Asset review specific checks ──
    if record.phase == "asset_review":
        layout = WorkspaceLayout(request.app.state.root_dir)
        job_dir = _find_job_dir(layout, project_id, job_id)
        try:
            clips = validate_assets(job_dir, force=payload.force)
            write_reviewed_snapshot(job_dir, clips)
            logger.info(
                f"[Review] 素材审核快照已保存: {job_dir / 'reviewed_assets.json'}"
            )
        except AssetValidationError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message)
        except FileNotFoundError:
            raise HTTPException(
                status_code=409,
                detail=(
                    "素材尚未收集完成（selected_clips.json 不存在），"
                    "请等待素材检索完成后重试"
                ),
            )

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
    project_id = _resolve_job_project(repo, job_id)
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
    layout = WorkspaceLayout(request.app.state.root_dir)
    project_id = request.query_params.get("project_id", "")

    job_dir = _find_job_dir(layout, project_id, job_id)
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
    layout = WorkspaceLayout(root_dir)
    project_id = request.query_params.get("project_id", "")

    job_dir = _find_job_dir(layout, project_id, job_id)

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
    """Reject a single clip and replace it with an alternative asset if available.

    This endpoint now serves as the single backend entry point for per-clip
    re-search. It reuses the shared ``select_replacement`` helper and always
    requires the job to be in the ``asset_review`` phase.
    """
    root_dir, _, job_dir = _resolve_job_context(request, job_id)
    record = _check_asset_review_phase(root_dir, job_id)
    clips = _load_clips(job_dir, payload.clip_index)

    entry = clips[payload.clip_index]
    sentence = entry.get("sentence", "")
    category = entry.get("category", "")
    rejected_asset_id = entry.get("asset_id", "")
    product = record.product or ""

    logger.info(
        f"[Review] 打回单个素材: job={job_id}, index={payload.clip_index}, "
        f"sentence={sentence[:30]}..., asset={rejected_asset_id}, "
        f"product={product}, category={category}"
    )

    # Blank clips are explicitly left empty by the user; do not overwrite them
    # with a random asset during re-search.
    if entry.get("visual_type") == "blank":
        return {
            "status": "clip_rejected",
            "job_id": job_id,
            "clip_index": payload.clip_index,
            "sentence": sentence,
            "replaced": False,
            "reason": "blank clip unchanged by re-search",
            "clip": entry,
        }

    asset_repo = _asset_repo(root_dir)
    decision = select_replacement(
        asset_repo,
        product=product,
        category=category,
        exclude_asset_id=rejected_asset_id,
    )

    if decision.chosen is None:
        logger.warning(
            f"[Review] 无替代素材: sentence={sentence[:30]}..., "
            f"category={category}, {decision.reason}"
        )
        _log_no_replacement(
            job_id,
            payload.clip_index,
            category,
            decision.reason,
            decision.diagnostics,
        )
        return {
            "status": "clip_rejected",
            "job_id": job_id,
            "clip_index": payload.clip_index,
            "sentence": sentence,
            "replaced": False,
            "reason": decision.reason,
            "diagnostics": (
                decision.diagnostics.__dict__ if decision.diagnostics else {}
            ),
            "clip": entry,
        }

    try:
        chosen = decision.chosen
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
        # Maintain the usage_count invariant: old asset is no longer referenced,
        # new asset is now referenced.
        asset_repo.decrement_usage(rejected_asset_id)
        asset_repo.increment_usage(chosen.asset_id)
        _save_clips(job_dir, clips)
        logger.info(
            f"[Review] 替换素材: {rejected_asset_id} → {chosen.asset_id}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Review] 替换素材失败: {e}")
        _log_replacement_error(
            job_id, payload.clip_index, category, e
        )
        # Best-effort: record that replacement failed. If this secondary write
        # also fails we still raise a 500 so the client sees an error rather
        # than an unhandled exception.
        try:
            clips[payload.clip_index]["method"] = "rejected_error"
            _save_clips(job_dir, clips)
        except Exception as save_exc:  # noqa: BLE001
            logger.warning(
                f"[Review] 标记 rejected_error 失败: {save_exc}"
            )
        raise HTTPException(
            status_code=500, detail=f"asset replacement failed: {e}"
        )

    return {
        "status": "clip_rejected",
        "job_id": job_id,
        "clip_index": payload.clip_index,
        "sentence": sentence,
        "replaced": True,
        "reason": "",
        "clip": clips[payload.clip_index],
    }


# ---------------------------------------------------------------------------
# Asset review shared helpers
# ---------------------------------------------------------------------------


def _resolve_job_context(request: Request, job_id: str) -> tuple[Path, str, Path]:
    """Resolve root_dir, project_id, job_dir from request and job_id."""
    root_dir = Path(request.app.state.root_dir)
    layout = WorkspaceLayout(root_dir)
    project_id = request.query_params.get("project_id", "")
    job_dir = _find_job_dir(layout, project_id, job_id)
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


def _check_asset_review_phase(root_dir: Path, job_id: str):
    """Raise 409 if the job is not in the asset_review phase.

    Returns the loaded JobRecord so callers can reuse fields like ``product``.
    """
    repo = FileStoreRepository(root_dir)
    project_id = _resolve_job_project(repo, job_id)
    record = repo.load_job(project_id, job_id)
    if record.phase != "asset_review":
        raise HTTPException(
            status_code=409,
            detail=f"asset mutations are only allowed during asset_review phase (current: {record.phase})",
        )
    return record


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


def _asset_repo(root_dir: Path):
    """Return an AssetRepository pointing at the workspace shared asset index."""
    from packages.pipeline_services.asset_library import AssetRepository

    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return AssetRepository(db_path)


def _log_no_replacement(
    job_id: str,
    clip_index: int,
    category: str,
    reason: str,
    diagnostics,
    log_dir: Path | None = None,
) -> None:
    """Persist a structured warning when no replacement asset is found."""
    log_error(
        {
            "source": "backend",
            "level": "warn",
            "message": (
                f"[AssetReview] 无替代素材: job={job_id}, "
                f"clip_index={clip_index}, category={category}, reason={reason}"
            ),
            "path": f"/api/reviews/{job_id}/reject-clip",
            "extra": {
                "job_id": job_id,
                "clip_index": clip_index,
                "category": category,
                "reason": reason,
                "diagnostics": (
                    diagnostics.__dict__ if diagnostics else {}
                ),
            },
        },
        log_dir=log_dir,
    )


def _log_replacement_error(
    job_id: str,
    clip_index: int,
    category: str,
    exc: Exception,
    log_dir: Path | None = None,
) -> None:
    """Persist a structured error log when replacement fails unexpectedly."""
    import traceback

    log_error(
        {
            "source": "backend",
            "level": "error",
            "message": (
                f"[AssetReview] 替换素材失败: job={job_id}, "
                f"clip_index={clip_index}, category={category}, error={exc}"
            ),
            "path": f"/api/reviews/{job_id}/reject-clip",
            "stack_trace": traceback.format_exc(),
            "extra": {
                "job_id": job_id,
                "clip_index": clip_index,
                "category": category,
                "error": str(exc),
            },
        },
        log_dir=log_dir,
    )


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
    """Manually assign a specific asset to a clip position.

    The client sends only the asset identifier; the server resolves and validates
    the asset metadata against the shared asset index.
    """
    root_dir, _, job_dir = _resolve_job_context(request, job_id)
    record = _check_asset_review_phase(root_dir, job_id)
    clips = _load_clips(job_dir, payload.clip_index)

    job_product = record.product or ""
    asset_repo = _asset_repo(root_dir)
    asset = asset_repo.query_one(payload.asset_id)
    if asset is None:
        raise HTTPException(
            status_code=404, detail=f"asset {payload.asset_id} not found in index"
        )
    if asset.status != "available":
        raise HTTPException(
            status_code=409,
            detail=f"asset {payload.asset_id} is not available",
        )
    if job_product and asset.product and job_product != asset.product:
        raise HTTPException(
            status_code=409,
            detail=(
                f"asset product '{asset.product}' does not match "
                f"job product '{job_product}'"
            ),
        )

    _ensure_original(clips, payload.clip_index)
    entry = clips[payload.clip_index]
    entry.update(
        {
            "file_path": asset.file_path,
            "asset_id": asset.asset_id,
            "duration_seconds": asset.duration_seconds,
            "category": asset.category,
            "method": "manual",
            "visual_type": "clip",
        }
    )
    # Preserve business fields that are not part of the asset metadata.
    entry.setdefault("requested_category", entry.get("category", ""))
    _save_clips(job_dir, clips)
    logger.info(
        f"[AssetReview] set-asset: job={job_id}, index={payload.clip_index}, "
        f"asset={asset.asset_id}"
    )
    return {
        "status": "set_asset",
        "job_id": job_id,
        "clip_index": payload.clip_index,
        "visual_type": "clip",
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
