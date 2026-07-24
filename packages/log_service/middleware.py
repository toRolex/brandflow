"""HTTP middleware that persists backend error/warning responses to JSONL logs.

The middleware captures every request/response.  For responses with a status code
of 4xx or 5xx it writes a structured entry to the persistent log via
`log_error()`.  Request bodies are only buffered when the client advertises a
small, known Content-Length, so large uploads and streaming requests are not
broken.
"""

from __future__ import annotations

import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from packages.log_service.log_writer import log_error

MAX_BODY_BYTES = 10_000
_METHODS_WITH_BODY = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def _safe_request_body(request: Request) -> str:
    """Return a small UTF-8 request body without consuming large streams.

    If the body size is unknown (no ``Content-Length``) or larger than
    ``MAX_BODY_BYTES``, an empty string is returned.  For small bodies the
    Starlette ``Request.body()`` cache is used so the route handler can still
    read the body afterwards.
    """
    if request.method not in _METHODS_WITH_BODY:
        return ""

    content_length = request.headers.get("content-length")
    if content_length is None:
        return ""

    try:
        length = int(content_length)
    except ValueError:
        return ""

    if length > MAX_BODY_BYTES:
        return ""

    try:
        body_bytes = await request.body()
    except Exception:  # noqa: BLE001
        return ""

    return body_bytes.decode("utf-8", errors="replace")


def _build_log_entry(
    request: Request,
    status_code: int,
    exc: BaseException | None = None,
    body: str = "",
) -> dict[str, Any]:
    """Build a structured log entry for a failed HTTP response."""
    level = "error" if status_code >= 500 else "warn"
    message = f"{request.method} {request.url.path} -> {status_code}"

    entry: dict[str, Any] = {
        "source": "backend",
        "level": level,
        "message": message,
        "status_code": status_code,
        "method": request.method,
        "path": request.url.path,
        "request_params": dict(request.query_params),
        "extra": {
            "client_host": request.client.host if request.client else None,
        },
    }

    if exc is not None:
        entry["stack_trace"] = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )

    if body:
        entry["request_body"] = body

    return entry


def install_log_middleware(app: FastAPI) -> None:
    """Register request/response logging middleware on *app*.

    All responses with a status code >= 400 are logged.  Exceptions that escape
    the route handlers are caught here so that the entry can include a stack
    trace and a clean 500 response can still be returned to the client.
    """

    @app.middleware("http")
    async def _log_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        body = await _safe_request_body(request)
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            entry = _build_log_entry(request, 500, exc=exc, body=body)
            log_error(entry)
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
            )

        if response.status_code >= 400:
            entry = _build_log_entry(request, response.status_code, body=body)
            log_error(entry)

        return response
