"""Runtime-log deletion service with date validation, today-protection,
file-lock safety, and idempotent deletion.

Security rules (issue #354):
- "Today" is defined using the same system local timezone as the log writer.
- Today's file is always protected — single-delete returns 400, batch places
  it in ``protected``.
- ``before_days <= 0`` is rejected.
- Filenames must match ``YYYY-MM-DD.jsonl`` and pass real calendar-date
  validation via ``date.fromisoformat()``.
- Deletion acquires the same ``_LOG_LOCK`` used by the writer so concurrent
  writes cannot observe a partially-deleted file.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, UTC
from pathlib import Path
from typing import Any, Literal

from packages.log_service.log_writer import _LOG_LOCK, get_log_dir

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _today_str() -> str:
    """Return the local-date string used by the log writer ("YYYY-MM-DD")."""
    return datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d")


def is_valid_calendar_date(date_str: str) -> bool:
    """True when *date_str* is a real calendar date (e.g. rejects 2026-02-30)."""
    if not _DATE_PATTERN.match(date_str):
        return False
    try:
        date.fromisoformat(date_str)
    except ValueError:
        return False
    return True


def _log_file_path(date_str: str) -> Path:
    """Return the full path to the JSONL log file for *date_str*."""
    return get_log_dir() / f"{date_str}.jsonl"


DeleteOutcome = Literal["deleted", "not_found", "protected"]


def _delete_date_safe(date_str: str) -> DeleteOutcome:
    """Classify and delete one Log Date atomically under the writer lock."""
    with _LOG_LOCK:
        if date_str == _today_str():
            return "protected"
        file_path = _log_file_path(date_str)
        if file_path.is_symlink() or not file_path.is_file():
            return "not_found"
        if file_path.suffix != ".jsonl":
            return "not_found"
        file_path.unlink()
        return "deleted"


def delete_single(date_str: str) -> dict[str, Any]:
    """Delete the log file for *date_str*.

    Returns ``{"date": date_str, "deleted": True/False}``.
    File-not-found is idempotent and returns ``deleted=False``.
    Today's date returns ``deleted=False, protected=True`` —
    callers do NOT need to enforce today-protection themselves.
    """
    if not is_valid_calendar_date(date_str):
        raise ValueError(f"Invalid Log Date: {date_str}")
    outcome = _delete_date_safe(date_str)
    if outcome == "protected":
        return {"date": date_str, "deleted": False, "protected": True}
    return {"date": date_str, "deleted": outcome == "deleted"}


def delete_batch(dates: list[str]) -> dict[str, Any]:
    """Delete multiple log files; today's date is placed in ``protected``.

    Returns::

      {"deleted": [...], "not_found": [...], "protected": [...]}
    """
    deleted: list[str] = []
    not_found: list[str] = []
    protected: list[str] = []

    for d in dates:
        if not is_valid_calendar_date(d):
            not_found.append(d)
            continue
        outcome = _delete_date_safe(d)
        if outcome == "deleted":
            deleted.append(d)
        elif outcome == "protected":
            protected.append(d)
        else:
            not_found.append(d)

    return {"deleted": deleted, "not_found": not_found, "protected": protected}


def cleanup(before_days: int) -> dict[str, Any]:
    """Delete log files strictly older than *before_days* before today.

    *before_days* must be >= 1 (0 and negative are rejected).
    Today's file is always protected.
    """
    if before_days < 1:
        raise ValueError("before_days must be >= 1")

    today_str = _today_str()
    today_date = date.fromisoformat(today_str)
    cutoff = today_date - timedelta(days=before_days)

    log_dir = get_log_dir()
    if not log_dir.exists():
        return {"deleted": [], "deleted_count": 0}

    deleted: list[str] = []
    for file_path in sorted(log_dir.glob("????-??-??.jsonl")):
        if not file_path.is_file():
            continue
        date_str = file_path.stem
        if not is_valid_calendar_date(date_str):
            continue
        file_date = date.fromisoformat(date_str)
        if file_date < cutoff:
            if _delete_date_safe(date_str) == "deleted":
                deleted.append(date_str)

    return {"deleted": deleted, "deleted_count": len(deleted)}
