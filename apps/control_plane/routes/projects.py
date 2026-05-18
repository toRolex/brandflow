from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["projects"])
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent.parent / "templates")
)


@router.get("/", response_class=HTMLResponse)
def project_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="projects.html",
        context={"projects": []},
    )
