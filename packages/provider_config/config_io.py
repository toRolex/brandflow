"""Shared file I/O helpers: load/save JSON config files with thread-safe atomic writes.

Replaces the ``_load()`` / ``_save()`` methods previously defined inside
the old config manager so that ``ConfigReader`` and other modules can share the
same safe I/O primitives.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

_io_lock = threading.Lock()


def load_config(path: str | Path) -> dict[str, Any]:
    """Read a JSON config file with thread-safety via ``threading.Lock``.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dict; empty dict when the file does not exist or is empty/corrupt.
    """
    with _io_lock:
        resolved = Path(path)
        if not resolved.exists():
            return {}
        try:
            with open(resolved, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        return raw


def save_config(path: str | Path, data: dict[str, Any]) -> None:
    """Write a JSON config file with **atomic, crash-safe** semantics.

    The payload is written to a temp file in the same directory (so the rename
    stays on the same file-system), then ``os.replace`` atomically swaps the
    temp file for the real path.  If the process crashes *before* the rename the
    original file is never touched.

    Thread-safety is guaranteed by the same ``_io_lock`` used by ``load_config``.
    """
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)

    with _io_lock:
        fd, tmp_name = tempfile.mkstemp(
            suffix=".json",
            prefix=".config_",
            dir=str(resolved.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp_name, str(resolved))
        except BaseException:
            # Clean up the temp file on any failure so we don't leak.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
