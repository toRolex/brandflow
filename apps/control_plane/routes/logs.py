"""API endpoints for submitting and downloading persistent error logs."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from packages.log_service.log_writer import get_log_dir, log_error

router = APIRouter(tags=["logs"])


class LogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    source: Literal["frontend", "backend"]
    level: Literal["error", "warn"]
    message: str
    timestamp: str | None = None
    status_code: int | None = None
    method: str | None = None
    path: str | None = None
    stack_trace: str | None = None
    request_body: str | None = None
    request_params: dict[str, str] | None = None
    extra: dict[str, Any] | None = None


@router.post("/error")
def report_error(entry: LogEntry) -> dict[str, bool]:
    log_error(entry.model_dump(exclude_none=True))
    return {"ok": True}


@router.get("/dates")
def list_dates() -> list[dict[str, int | str]]:
    log_dir = get_log_dir()
    if not log_dir.exists():
        return []
    files = sorted(
        (p for p in log_dir.glob("????-??-??.jsonl") if p.is_file()), reverse=True
    )
    return [
        {
            "date": file.stem,
            "size_bytes": file.stat().st_size,
            "error_count": sum(1 for _ in file.open(encoding="utf-8")),
        }
        for file in files
    ]


@router.get("/download")
def download_log(
    date_value: str = Query(alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> FileResponse:
    try:
        date.fromisoformat(date_value)
    except ValueError as exc:
        raise HTTPException(400, "Invalid date") from exc
    file = get_log_dir() / f"{date_value}.jsonl"
    if not file.is_file():
        raise HTTPException(404, "Log file not found")
    return FileResponse(file, media_type="application/x-ndjson", filename=file.name)
