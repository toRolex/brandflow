"""Persist uncaught backend exceptions without hiding their normal stderr output."""

from __future__ import annotations

import sys
import traceback
from collections.abc import Callable
from typing import Any, cast

from packages.log_service.log_writer import log_error

ExceptionHook = Callable[[type[BaseException], BaseException | None, Any], None]


def _wrap_excepthook(delegate: ExceptionHook) -> ExceptionHook:
    def log_excepthook(
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
        delegate(exc_type, exc_value, exc_tb)

    log_excepthook._brandflow_log_hook = True  # type: ignore[attr-defined]
    return log_excepthook


def install_global_excepthook() -> None:
    """Wrap the active process exception hook without stacking wrappers."""
    current_hook = cast(ExceptionHook, sys.excepthook)
    if getattr(current_hook, "_brandflow_log_hook", False):
        return
    sys.excepthook = _wrap_excepthook(current_hook)
