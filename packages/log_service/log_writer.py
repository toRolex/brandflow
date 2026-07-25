"""Thread-safe JSONL writer for persistent error logs."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

_LOG_LOCK = threading.Lock()


def get_log_dir() -> Path:
    """Return the OS-specific directory containing daily Brandflow logs."""
    return Path(user_data_dir("brandflow", appauthor=False, roaming=True)) / "logs"


def log_error(entry: dict[str, Any], log_dir: Path | None = None) -> Path:
    """Append an error entry to the current local-date JSONL file and flush it."""
    target_dir = log_dir or get_log_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=UTC).astimezone()
    payload = {**entry, "timestamp": entry.get("timestamp") or now.isoformat()}
    target = target_dir / f"{now:%Y-%m-%d}.jsonl"
    with _LOG_LOCK, target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        stream.flush()
    return target
