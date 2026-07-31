"""FastAPI middleware for recording failed HTTP requests."""

from __future__ import annotations

import json
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from packages.log_service.log_writer import log_error

_LOG_REPORT_PATH = "/api/logs/error"


async def _request_body(request: Request) -> Any | None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    try:
        raw_body = await request.body()
    except RuntimeError:
        return None
    if not raw_body:
        return None
    decoded_body = raw_body.decode("utf-8", errors="replace")
    if request.headers.get("content-type", "").partition(";")[0] == "application/json":
        try:
            return json.loads(decoded_body)
        except json.JSONDecodeError:
            pass
    return decoded_body


def _build_error_log_entry(
    request: Request, status_code: int, body: Any | None, exc: Exception | None = None
) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "client_host": request.client.host if request.client else None,
    }
    request_id = request.headers.get("x-request-id")
    if request_id:
        extra["request_id"] = request_id
    result: dict[str, Any] = {
        "source": "backend",
        "level": (
            "error" if status_code >= 500 else "info" if status_code == 404 else "warn"
        ),
        "message": f"{request.method} {request.url.path} -> {status_code}",
        "status_code": status_code,
        "method": request.method,
        "path": request.url.path,
        "request_params": dict(request.query_params),
        "extra": extra,
    }
    if body is not None:
        result["request_body"] = body
    if exc:
        result["stack_trace"] = "".join(traceback.format_exception(exc))
    return result


def install_log_middleware(app: FastAPI) -> None:
    """Install logging once; requests to the logging API do not self-log."""

    @app.exception_handler(StarletteHTTPException)
    async def record_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        if request.url.path != _LOG_REPORT_PATH:
            body = getattr(request.state, "runtime_log_request_body", None)
            log_error(
                _build_error_log_entry(
                    request,
                    exc.status_code,
                    body,
                    exc if exc.status_code >= 500 else None,
                )
            )
            request.state.runtime_error_logged = True
        return await http_exception_handler(request, exc)

    @app.middleware("http")
    async def record_errors(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        body = await _request_body(request)
        request.state.runtime_log_request_body = body
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            if request.url.path != _LOG_REPORT_PATH:
                log_error(_build_error_log_entry(request, 500, body, exc))
            raise
        if (
            response.status_code >= 400
            and request.url.path != _LOG_REPORT_PATH
            and not getattr(request.state, "runtime_error_logged", False)
        ):
            log_error(_build_error_log_entry(request, response.status_code, body))
        return response
