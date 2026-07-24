"""Log management REST API for the control plane."""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from packages.log_service.log_writer import get_log_dir, log_error

router = APIRouter(tags=["logs"])

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LogEntry(BaseModel):
    """Structured error log entry submitted by clients or internal services."""

    model_config = ConfigDict(extra="allow")

    source: str = Field(..., description="Component that emitted the log entry.")
    level: str = Field(..., description="Log level, e.g. error, warn, info.")
    message: str = Field(..., description="Human-readable log message.")
    timestamp: str | None = Field(
        default=None,
        description="ISO-8601 timestamp; injected automatically if omitted.",
    )
    request_id: str | None = Field(
        default=None,
        description="Optional correlation/request identifier.",
    )
    context: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured context dictionary.",
    )
    error: dict[str, Any] | None = Field(
        default=None,
        description="Optional error detail dictionary.",
    )


class LogDateInfo(BaseModel):
    """Metadata for a single daily JSONL log file."""

    date: str
    size_bytes: int
    error_count: int


@router.post("/error", status_code=201)
def report_error(entry: LogEntry) -> dict[str, bool]:
    """Accept a structured log entry and persist it to today's JSONL log file."""
    payload = entry.model_dump(exclude_unset=False, exclude_none=False)
    log_error(payload, log_dir=None)
    return {"ok": True}


@router.get("/dates", response_model=list[LogDateInfo])
def list_dates() -> list[LogDateInfo]:
    """List all daily JSONL log files, newest first."""
    log_dir = get_log_dir()
    if not log_dir.exists():
        return []

    files = sorted(
        (
            p
            for p in log_dir.iterdir()
            if p.is_file() and p.suffix == ".jsonl" and _DATE_RE.match(p.stem)
        ),
        key=lambda p: p.stem,
        reverse=True,
    )

    return [
        LogDateInfo(
            date=f.stem,
            size_bytes=f.stat().st_size,
            error_count=_count_jsonl_lines(f),
        )
        for f in files
    ]


@router.get("/download")
def download_error_log(
    date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
) -> FileResponse:
    """Download the JSONL log file for a specific date."""
    try:
        datetime.date.fromisoformat(date)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date: {date}",
        ) from exc

    log_file = get_log_dir() / f"{date}.jsonl"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")

    return FileResponse(
        log_file,
        media_type="application/x-ndjson",
        filename=f"{date}.jsonl",
    )


def _count_jsonl_lines(path: Path) -> int:
    """Count the number of newline-delimited JSON records in *path*."""
    count = 0
    with path.open("r", encoding="utf-8") as f:
        for _ in f:
            count += 1
    return count
