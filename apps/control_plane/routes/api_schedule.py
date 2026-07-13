from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from apps.control_plane.services.schedule_store import ScheduleStore

router = APIRouter(prefix="/api/schedule", tags=["api-schedule"])


def _get_store(request: Request) -> ScheduleStore:
    return ScheduleStore.get(Path(request.app.state.root_dir))


@router.get("")
def list_schedule(
    request: Request,
    project_id: str | None = Query(default=None),
    platform: str | None = Query(default=None),
):
    return _get_store(request).list(project_id=project_id, platform=platform)


@router.get("/export")
def export_schedule(request: Request):
    store = _get_store(request)
    entries = store.list()
    wb = Workbook()
    ws = wb.active
    ws.title = "排期池"
    ws.append(["ID", "Job ID", "平台", "标题", "简介", "状态", "创建时间"])
    for e in entries:
        ws.append(
            [
                e["id"],
                e["job_id"],
                e["platform"],
                e["title"],
                e["description"],
                e["status"],
                e["created_at"],
            ]
        )
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=schedule.xlsx"},
    )
