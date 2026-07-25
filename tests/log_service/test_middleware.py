import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
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
    assert record["level"] == "warn"


def test_middleware_persists_a_5xx_response_with_stack_trace(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("packages.log_service.log_writer.get_log_dir", lambda: tmp_path)
    app = FastAPI()
    install_log_middleware(app)

    @app.get("/broken")
    async def broken() -> None:
        raise RuntimeError("unexpected failure")

    assert TestClient(app).get("/broken").status_code == 500
    record = json.loads(next(tmp_path.glob("*.jsonl")).read_text(encoding="utf-8"))
    assert record["status_code"] == 500
    assert record["level"] == "error"
    assert "RuntimeError" in record["stack_trace"]
