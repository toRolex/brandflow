"""Persist uncaught backend exceptions without hiding their normal stderr output."""

from __future__ import annotations

import sys
import traceback
from typing import Any

from packages.log_service.log_writer import log_error

_original_excepthook: Any | None = None


def _log_excepthook(
    exc_type: type[BaseException], exc_value: BaseException | None, exc_tb: Any
) -> None:
    if exc_value is not None:
        log_error(
            {
                "source": "backend",
                "level": "error",
                "message": str(exc_value),
                "stack_trace": "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                ),
            }
        )
    if _original_excepthook is not None:
        _original_excepthook(exc_type, exc_value, exc_tb)


def install_global_excepthook() -> None:
    """Idempotently wrap the process exception hook."""
    global _original_excepthook
    if _original_excepthook is None:
        _original_excepthook = sys.excepthook
    sys.excepthook = _log_excepthook
