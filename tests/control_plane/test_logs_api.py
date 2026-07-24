from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.control_plane.routes.logs import router as logs_router


class _FakePlatformDirs:
    """Stand-in for platformdirs.user_data_dir that returns a test directory."""

    def __init__(self, base: Path) -> None:
        self.base = base

    def __call__(self, app: str, appauthor: bool | None = None) -> str:
        return str(self.base)


@pytest.fixture
def log_dir(tmp_path: Path) -> Path:
    return tmp_path / "logs"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Build a TestClient whose logs are written into a temporary directory."""
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        _FakePlatformDirs(tmp_path),
    )
    app = FastAPI()
    app.include_router(logs_router, prefix="/api/logs")
    return TestClient(app)


def _today_filename() -> str:
    return f"{datetime.now(tz=UTC).astimezone().date().isoformat()}.jsonl"


def test_post_error_creates_jsonl_entry(client: TestClient, log_dir: Path) -> None:
    payload = {
        "source": "control_plane",
        "level": "error",
        "message": "something went wrong",
        "context": {"endpoint": "/api/jobs"},
    }

    response = client.post("/api/logs/error", json=payload)

    assert response.status_code == 201
    assert response.json() == {"ok": True}

    log_file = log_dir / _today_filename()
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["source"] == "control_plane"
    assert stored["level"] == "error"
    assert stored["message"] == "something went wrong"
    assert stored["context"] == {"endpoint": "/api/jobs"}
    assert "timestamp" in stored


def test_get_dates_lists_files_sorted_descending(
    client: TestClient, log_dir: Path
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    older = log_dir / "2026-07-20.jsonl"
    older.write_bytes(
        (
            json.dumps({"message": "first"}) + "\n" + json.dumps({"message": "second"}) + "\n"
        ).encode("utf-8"),
    )
    newer = log_dir / "2026-07-21.jsonl"
    newer.write_bytes(
        (json.dumps({"message": "third"}) + "\n").encode("utf-8"),
    )

    response = client.get("/api/logs/dates")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0] == {
        "date": "2026-07-21",
        "size_bytes": newer.stat().st_size,
        "error_count": 1,
    }
    assert payload[1] == {
        "date": "2026-07-20",
        "size_bytes": older.stat().st_size,
        "error_count": 2,
    }


def test_get_dates_returns_empty_list_when_directory_missing(
    client: TestClient, log_dir: Path
) -> None:
    assert not log_dir.exists()
    response = client.get("/api/logs/dates")
    assert response.status_code == 200
    assert response.json() == []


def test_download_existing_log_file(client: TestClient, log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "2026-07-20.jsonl"
    log_file.write_bytes(
        (
            json.dumps({"message": "first"}) + "\n" + json.dumps({"message": "second"}) + "\n"
        ).encode("utf-8"),
    )

    response = client.get("/api/logs/download?date=2026-07-20")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-ndjson"
    assert "2026-07-20.jsonl" in response.headers["content-disposition"]
    assert response.text == log_file.read_text(encoding="utf-8")


def test_download_missing_log_file_returns_404(client: TestClient) -> None:
    response = client.get("/api/logs/download?date=2026-07-20")
    assert response.status_code == 404


def test_download_invalid_date_format_returns_422(client: TestClient) -> None:
    response = client.get("/api/logs/download?date=07-20-2026")
    assert response.status_code == 422
