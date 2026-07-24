"""Persistent JSONL error log writer.

Logs are stored as one JSON object per line, isolated by local server date,
in the OS application data directory (e.g. %LOCALAPPDATA%/brandflow/logs on
Windows). Each write is flushed immediately so recent entries survive a crash.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir


def get_log_dir() -> Path:
    """Return the directory where daily log files are stored."""
    return Path(user_data_dir("brandflow", appauthor=False)) / "logs"


_LOG_LOCK = threading.Lock()


def log_error(entry: dict[str, Any], log_dir: Path | None = None) -> Path:
    """Append *entry* to today's JSONL log file.

    Args:
        entry: Structured error record. A ``timestamp`` field is injected
            automatically if missing.
        log_dir: Optional override for the log directory. Intended for tests.

    Returns:
        The path of the log file that was written.
    """
    if log_dir is None:
        log_dir = get_log_dir()

    log_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=UTC).astimezone()
    date_str = now.strftime("%Y-%m-%d")
    log_file = log_dir / f"{date_str}.jsonl"

    if "timestamp" not in entry:
        entry["timestamp"] = now.isoformat()

    line = json.dumps(entry, ensure_ascii=False, default=str, sort_keys=False)

    with _LOG_LOCK, log_file.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()

    return log_file
