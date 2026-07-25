"""FastAPI middleware for recording failed HTTP requests."""

from __future__ import annotations

import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from packages.log_service.log_writer import log_error

MAX_BODY_BYTES = 10_000


async def _request_body(request: Request) -> str:
    length = request.headers.get("content-length")
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"} or length is None:
        return ""
    try:
        if int(length) > MAX_BODY_BYTES:
            return ""
        return (await request.body()).decode("utf-8", errors="replace")
    except (ValueError, RuntimeError):
        return ""


def _build_error_log_entry(
    request: Request, status_code: int, body: str, exc: Exception | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "source": "backend",
        "level": "error" if status_code >= 500 else "warn",
        "message": f"{request.method} {request.url.path} -> {status_code}",
        "status_code": status_code,
        "method": request.method,
        "path": request.url.path,
        "request_params": dict(request.query_params),
        "extra": {"client_host": request.client.host if request.client else None},
    }
    if body:
        result["request_body"] = body
    if exc:
        result["stack_trace"] = "".join(traceback.format_exception(exc))
    return result


def install_log_middleware(app: FastAPI) -> None:
    """Install logging once; requests to the logging API do not self-log."""

    @app.middleware("http")
    async def record_errors(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        body = await _request_body(request)
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            log_error(_build_error_log_entry(request, 500, body, exc))
            return JSONResponse(
                status_code=500, content={"detail": "Internal Server Error"}
            )
        if response.status_code >= 400:
            log_error(_build_error_log_entry(request, response.status_code, body))
        return response
