from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

router = APIRouter(prefix="/jobs", tags=["jobs"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


class ResumeRequest(BaseModel):
    phase: str


@router.get("/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: str, request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="job_detail.html",
        context={"job_id": job_id},
    )


@router.post("/{job_id}/resume-from-phase")
def resume_from_phase(job_id: str, payload: ResumeRequest) -> dict[str, str]:
    return {
        "job_id": job_id,
        "phase": payload.phase,
        "status": "queued_for_retry",
    }
