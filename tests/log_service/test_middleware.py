import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from packages.log_service.middleware import install_log_middleware


def test_middleware_persists_a_4xx_response(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/missing")
    async def missing() -> None:
        raise HTTPException(status_code=404)

    assert TestClient(app).get("/missing").status_code == 404
    record = json.loads(next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8"))
    assert record["status_code"] == 404
    assert record["level"] == "info"


def test_middleware_persists_a_5xx_response_with_stack_trace(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/broken")
    async def broken() -> None:
        raise RuntimeError("unexpected failure")

    assert (
        TestClient(app, raise_server_exceptions=False).get("/broken").status_code == 500
    )
    record = json.loads(next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8"))
    assert record["status_code"] == 500
    assert record["level"] == "error"
    assert "RuntimeError" in record["stack_trace"]


def test_middleware_persists_http_500_with_stack_trace(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/broken")
    async def broken() -> None:
        raise HTTPException(status_code=500, detail="expected failure")

    response = TestClient(app, raise_server_exceptions=False).get("/broken")

    assert response.status_code == 500
    assert response.json() == {"detail": "expected failure"}
    record = json.loads(next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8"))
    assert "HTTPException" in record["stack_trace"]
    assert "expected failure" in record["stack_trace"]


def test_middleware_preserves_the_application_exception_handler(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    app = FastAPI()
    install_log_middleware(app)

    @app.exception_handler(Exception)
    async def handle_runtime_error(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/broken")
    async def broken() -> None:
        raise RuntimeError("custom failure")

    response = TestClient(app, raise_server_exceptions=False).get("/broken")

    assert response.status_code == 503
    assert response.json() == {"detail": "custom failure"}


def test_middleware_preserves_large_json_request_body(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    app = FastAPI()
    install_log_middleware(app)

    @app.post("/invalid")
    async def invalid() -> JSONResponse:
        return JSONResponse({"detail": "invalid"}, status_code=400)

    payload = {"text": "x" * 20_000}
    assert TestClient(app).post("/invalid", json=payload).status_code == 400
    record = json.loads(next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8"))
    assert record["request_body"] == payload


def test_middleware_does_not_persist_a_2xx_response(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    assert TestClient(app).get("/ok").status_code == 200
    assert list(tmp_path.glob("*.jsonl")) == []


def test_middleware_persists_get_request_params(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/missing")
    async def missing() -> None:
        raise HTTPException(status_code=404)

    assert TestClient(app).get("/missing", params={"key": "value"}).status_code == 404
    record = json.loads(next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8"))
    assert record["request_params"] == {"key": "value"}
