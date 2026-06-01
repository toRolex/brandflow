import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from packages.domain_core.state import next_phase
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.legacy_script_bridge import LegacyScriptBridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["reviews"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


class ReviewAction(BaseModel):
    review_gate: str


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
    for project_dir in repo.root.joinpath("workspace", "projects").iterdir():
        if not project_dir.is_dir():
            continue
        try:
            repo.load_job(project_dir.name, job_id)
            return project_dir.name
        except Exception:
            continue
    return None


@router.get("/{job_id}", response_class=HTMLResponse)
def review_detail(job_id: str, request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="review_detail.html",
        context={"job_id": job_id},
    )


@router.post("/{job_id}/approve")
def approve_review(job_id: str, payload: ReviewAction, request: Request) -> dict:
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    try:
        nxt = next_phase(record.phase)
    except ValueError:
        nxt = "completed"
    repo.save_job(project_id, record.model_copy(update={"phase": nxt, "review_status": "approved"}))
    repo.append_review_event(project_id, {"job_id": job_id, "gate": payload.review_gate, "action": "approved"})
    logger.info(f"[Review] 审核通过: job={job_id}, phase={record.phase} → {nxt}")
    return {"status": "approved", "job_id": job_id, "next_phase": nxt}


@router.post("/{job_id}/reject")
def reject_review(job_id: str, payload: ReviewAction, request: Request) -> dict:
    repo = FileStoreRepository(request.app.state.root_dir)
    project_id = _find_job_project(repo, job_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="job not found")
    record = repo.load_job(project_id, job_id)
    repo.save_job(
        project_id,
        record.model_copy(update={"phase": "queued", "review_status": "none"}),
    )
    dispatcher = request.app.state.dispatcher
    dispatcher.enqueue_demo_job(project_id, job_id)
    repo.append_review_event(project_id, {"job_id": job_id, "gate": payload.review_gate, "action": "rejected"})
    logger.info(f"[Review] 打回重做: job={job_id}")
    return {"status": "rejected", "job_id": job_id, "next_phase": "queued"}


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
            json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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

    logger.info(f"[Review] 附带提示词重新生成: job={job_id}, product={product}, prompt={payload.custom_prompt[:50]}...")

    try:
        bridge = LegacyScriptBridge(root_dir)
        result = bridge.generate(
            product=product,
            output_dir=job_dir,
            mock=False,
            custom_prompt=payload.custom_prompt,
        )
        logger.info(f"[Review] 重新生成成功: job={job_id}, txt={result.get('txt_path')}")
        return {
            "job_id": job_id,
            "status": "regenerated",
            "result": result,
        }
    except Exception as e:
        logger.error(f"[Review] 重新生成失败: job={job_id}, error={e}")
        raise HTTPException(status_code=500, detail=f"Script generation failed: {e}")
