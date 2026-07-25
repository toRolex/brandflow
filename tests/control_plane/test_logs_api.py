import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.control_plane.routes.logs import router


def test_log_api_persists_lists_and_downloads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/logs")
    client = TestClient(app)

    response = client.post(
        "/api/logs/error",
        json={"source": "frontend", "level": "error", "message": "boom"},
    )
    assert response.status_code == 201
    assert response.json() == {"ok": True}
    date = next((tmp_path / "logs").glob("*.jsonl")).stem
    assert client.get("/api/logs/dates").json()[0]["error_count"] == 1
    response = client.get(f"/api/logs/download?date={date}")
    assert response.status_code == 200
    assert response.headers["content-type"] in ("application/x-ndjson", "text/plain")
    assert f"{date}.jsonl" in response.headers["content-disposition"]
    assert json.loads(response.text)["message"] == "boom"


def test_log_api_rejects_invalid_entries_and_missing_download(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/logs")
    client = TestClient(app)

    assert (
        client.post("/api/logs/error", json={"message": "missing fields"}).status_code
        == 400
    )
    assert client.get("/api/logs/dates").json() == []
    assert client.get("/api/logs/download?date=2026-07-25").status_code == 404


def test_log_api_accepts_large_frontend_reports_and_sorts_dates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "2026-07-24.jsonl").write_text('{"message":"older"}\n')
    (log_dir / "2026-07-25.jsonl").write_text('{"message":"newer"}\n')
    app = FastAPI()
    app.include_router(router, prefix="/api/logs")
    client = TestClient(app)

    response = client.post(
        "/api/logs/error",
        json={
            "source": "frontend",
            "level": "error",
            "message": "x" * 20_000,
        },
    )

    assert response.status_code == 201
    assert [entry["date"] for entry in client.get("/api/logs/dates").json()] == [
        "2026-07-25",
        "2026-07-24",
    ]


def test_log_api_preserves_object_request_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/logs")
    client = TestClient(app)

    response = client.post(
        "/api/logs/error",
        json={
            "source": "frontend",
            "level": "error",
            "message": "request failed",
            "request_body": {"product": "demo", "scene": 3},
        },
    )

    assert response.status_code == 201
    record = json.loads(next((tmp_path / "logs").glob("*.jsonl")).read_text())
    assert record["request_body"] == {"product": "demo", "scene": 3}
