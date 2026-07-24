from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from packages.log_service.middleware import install_log_middleware


@pytest.fixture
def _log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(
        "packages.log_service.log_writer.get_log_dir",
        lambda: log_dir,
    )
    yield log_dir


def _latest_log_file(log_dir: Path) -> Path:
    return log_dir / f"{datetime.now(tz=UTC).astimezone().date().isoformat()}.jsonl"


def test_middleware_logs_4xx_warning(_log_dir: Path) -> None:
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/items/{item_id}")
    async def read_item(item_id: int) -> dict:
        if item_id == 0:
            raise HTTPException(status_code=404, detail="not found")
        return {"item_id": item_id}

    client = TestClient(app)
    response = client.get("/items/0")

    assert response.status_code == 404
    log_file = _latest_log_file(_log_dir)
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source"] == "backend"
    assert parsed["level"] == "warn"
    assert parsed["status_code"] == 404
    assert parsed["method"] == "GET"
    assert parsed["path"] == "/items/0"
    assert parsed["message"] == "GET /items/0 -> 404"
    assert parsed["request_params"] == {}


def test_middleware_logs_5xx_error_with_stack_trace(_log_dir: Path) -> None:
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("server exploded")

    client = TestClient(app)
    response = client.get("/boom")

    assert response.status_code == 500
    log_file = _latest_log_file(_log_dir)
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["source"] == "backend"
    assert parsed["level"] == "error"
    assert parsed["status_code"] == 500
    assert parsed["message"] == "GET /boom -> 500"
    assert "stack_trace" in parsed
    assert "RuntimeError" in parsed["stack_trace"]
    assert "server exploded" in parsed["stack_trace"]


def test_middleware_skips_2xx_responses(_log_dir: Path) -> None:
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/ok")
    async def ok() -> dict:
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ok")

    assert response.status_code == 200
    assert not _latest_log_file(_log_dir).exists()


def test_middleware_logs_request_body_and_query_params(_log_dir: Path) -> None:
    app = FastAPI()
    install_log_middleware(app)

    @app.post("/validate")
    async def validate(payload: dict) -> dict:
        if payload.get("valid"):
            return {"ok": True}
        raise HTTPException(status_code=400, detail="bad request")

    client = TestClient(app)
    response = client.post(
        "/validate",
        json={"valid": False},
        params={"source": "test"},
    )

    assert response.status_code == 400
    log_file = _latest_log_file(_log_dir)
    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["request_body"] == '{"valid":false}'
    assert parsed["request_params"] == {"source": "test"}


def test_middleware_does_not_break_large_request_body(_log_dir: Path) -> None:
    app = FastAPI()
    install_log_middleware(app)

    @app.post("/echo")
    async def echo(payload: dict) -> dict:
        return payload

    client = TestClient(app)
    big_value = "x" * 20_000
    response = client.post("/echo", json={"data": big_value})

    assert response.status_code == 200
    assert response.json() == {"data": big_value}
    assert not _latest_log_file(_log_dir).exists()
