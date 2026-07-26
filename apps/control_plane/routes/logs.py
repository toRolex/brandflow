"""API endpoints for submitting, listing, downloading and deleting persistent
error logs (#354).
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, ValidationError

from packages.log_service import log_deletion
from packages.log_service.log_writer import get_log_dir, log_error
from packages.pagination import DEFAULT_PAGE_SIZE, paginated, slice_indices

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
    request_body: Any | None = None
    request_params: dict[str, str] | None = None
    extra: dict[str, Any] | None = None


class BatchDeleteRequest(BaseModel):
    dates: list[str]


def _validate_date_str(date_str: str) -> None:
    """Raise 400 if *date_str* is not a real calendar date."""
    if not log_deletion.is_valid_calendar_date(date_str):
        raise HTTPException(400, f"Invalid date: {date_str}")


# ── write ──────────────────────────────────────────────────────────────────


@router.post("/error", status_code=201)
def report_error(entry: dict[str, Any] = Body(...)) -> dict[str, bool]:
    try:
        validated_entry = LogEntry.model_validate(entry)
    except ValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=exc.errors(include_url=False),
        ) from exc
    log_error(validated_entry.model_dump(exclude_none=True))
    return {"ok": True}


# ── list ───────────────────────────────────────────────────────────────────


def _parse_log_date_info(file_path: Any) -> dict[str, int | str]:
    return {
        "date": file_path.stem,
        "size_bytes": file_path.stat().st_size,
        "error_count": sum(1 for _ in file_path.open(encoding="utf-8")),
    }


@router.get("/dates")
def list_dates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
) -> dict[str, Any]:
    """Return paginated log-date summaries, newest first."""
    log_dir = get_log_dir()
    if not log_dir.exists():
        return paginated([], 0, page, page_size)

    all_files = sorted(
        (p for p in log_dir.glob("????-??-??.jsonl") if p.is_file()),
        key=lambda f: f.stem,
        reverse=True,
    )
    total = len(all_files)
    start, end = slice_indices(total, page, page_size)
    items = [_parse_log_date_info(f) for f in all_files[start:end]]
    return paginated(items, total, page, page_size)


# ── download ───────────────────────────────────────────────────────────────


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


# ── delete (static routes MUST come before dynamic /{date}) ────────────────


@router.delete("/batch")
def delete_logs_batch(payload: BatchDeleteRequest) -> dict[str, Any]:
    """Delete multiple log files (1–200 dates).

    Today's date is placed in ``protected``, non-existent dates in
    ``not_found`` — neither blocks other dates from being processed.
    """
    dates = payload.dates
    if not dates or len(dates) > 200:
        raise HTTPException(400, "dates must contain 1–200 entries")
    for d in dates:
        _validate_date_str(d)
    return log_deletion.delete_batch(dates)


@router.delete("/cleanup")
def cleanup_logs(
    before_days: int = Query(ge=1),
) -> dict[str, Any]:
    """Delete log files strictly older than *before_days* before today.

    ``before_days`` must be >= 1 (0 or negative is rejected).
    """
    return log_deletion.cleanup(before_days)


@router.delete("/{date_str}")
def delete_log_date(date_str: str) -> dict[str, Any]:
    """Delete a single day's log file.  Today → 400."""
    _validate_date_str(date_str)
    result = log_deletion.delete_single(date_str)
    if result.get("protected"):
        raise HTTPException(400, "Cannot delete today's log file")
    return result
