"""Global uncaught-exception hook that persists backend errors to JSONL logs.

Install with `install_global_excepthook()` once at process start.  The original
``sys.excepthook`` is kept so the exception is still printed to ``stderr``.
"""

from __future__ import annotations

import sys
import traceback
from typing import Any

from packages.log_service.log_writer import log_error

_original_excepthook: Any | None = None


def _log_excepthook(
    exc_type: type[BaseException],
    exc_value: BaseException | None,
    exc_tb: Any,
) -> None:
    """Log uncaught exceptions and forward to the original excepthook."""
    if exc_value is not None:
        stack_trace = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        entry = {
            "source": "backend",
            "level": "error",
            "message": str(exc_value),
            "stack_trace": stack_trace,
        }
        log_error(entry)

    if _original_excepthook is not None:
        _original_excepthook(exc_type, exc_value, exc_tb)


def install_global_excepthook() -> None:
    """Replace ``sys.excepthook`` with the logging wrapper.

    The previously installed hook is preserved so it is still invoked after
    the log entry is written.  Calling this function more than once is safe
    (idempotent).
    """
    global _original_excepthook

    if _original_excepthook is None:
        _original_excepthook = sys.excepthook

    sys.excepthook = _log_excepthook
