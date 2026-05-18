from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

router = APIRouter(prefix="/reviews", tags=["reviews"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


class ReviewAction(BaseModel):
    review_gate: str


@router.get("/{job_id}", response_class=HTMLResponse)
def review_detail(job_id: str, request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="review_detail.html",
        context={"job_id": job_id},
    )


@router.post("/{job_id}/approve")
def approve_review(job_id: str, payload: ReviewAction) -> dict[str, str]:
    return {
        "job_id": job_id,
        "review_gate": payload.review_gate,
        "status": "approved",
    }


@router.post("/{job_id}/reject")
def reject_review(job_id: str, payload: ReviewAction) -> dict[str, str]:
    return {
        "job_id": job_id,
        "review_gate": payload.review_gate,
        "status": "rejected",
    }
