import json
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.control_plane.routes.logs import router


def _write_log_entry(log_dir: Path, date_str: str, data: dict) -> None:
    """Write a single JSON line to *date_str*.jsonl under *log_dir*."""
    log_dir.mkdir(parents=True, exist_ok=True)
    file = log_dir / f"{date_str}.jsonl"
    line = json.dumps(data, ensure_ascii=False) + "\n"
    with file.open("a", encoding="utf-8") as fh:
        fh.write(line)


def test_log_api_persists_lists_and_downloads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        "packages.log_service.log_deletion.get_log_dir",
        lambda: tmp_path / "logs",
    )
    # Freeze "today" for the deletion service so the log file is deletable
    test_today = date.today().isoformat()
    monkeypatch.setattr(
        "packages.log_service.log_deletion._today_str",
        lambda: test_today,
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
    date_str = next((tmp_path / "logs").glob("*.jsonl")).stem

    dates_resp = client.get("/api/logs/dates").json()
    assert dates_resp["items"][0]["error_count"] == 1

    response = client.get(f"/api/logs/download?date={date_str}")
    assert response.status_code == 200
    assert response.headers["content-type"] in ("application/x-ndjson", "text/plain")
    assert f"{date_str}.jsonl" in response.headers["content-disposition"]
    assert json.loads(response.text)["message"] == "boom"


def test_log_api_rejects_invalid_entries_and_missing_download(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        "packages.log_service.log_deletion.get_log_dir",
        lambda: tmp_path / "logs",
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/logs")
    client = TestClient(app)

    assert (
        client.post("/api/logs/error", json={"message": "missing fields"}).status_code
        == 400
    )
    resp = client.get("/api/logs/dates").json()
    assert resp == {"items": [], "total": 0, "page": 1, "page_size": 10}
    # missing download — use a reference date, not hardcoded
    ref_date = (date.today() - timedelta(days=1)).isoformat()
    assert client.get(f"/api/logs/download?date={ref_date}").status_code == 404


def test_log_api_accepts_large_frontend_reports_and_sorts_dates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        "packages.log_service.log_deletion.get_log_dir",
        lambda: tmp_path / "logs",
    )
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # Use dynamic dates relative to a fixed reference to avoid hardcoded-date brittleness
    ref = date(2026, 7, 25)
    older = (ref - timedelta(days=1)).isoformat()
    newer = ref.isoformat()

    _write_log_entry(log_dir, older, {"message": "older"})
    _write_log_entry(log_dir, newer, {"message": "newer"})

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
    # The response is paginated; extract the date list from items
    items = client.get("/api/logs/dates").json()["items"]
    dates = [entry["date"] for entry in items]
    # Today's file (from log_error) plus our two pre-created files
    assert newer in dates
    assert older in dates
    # Newest first
    assert dates == sorted(dates, reverse=True)


def test_log_api_preserves_object_request_body(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        "packages.log_service.log_deletion.get_log_dir",
        lambda: tmp_path / "logs",
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


def test_log_delete_api_enforces_single_and_batch_safety(
    tmp_path: Path, monkeypatch
) -> None:
    log_dir = tmp_path / "logs"
    today = date(2026, 7, 26)
    deletable = (today - timedelta(days=1)).isoformat()
    missing = (today - timedelta(days=2)).isoformat()
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    monkeypatch.setattr(
        "packages.log_service.log_deletion.get_log_dir",
        lambda: log_dir,
    )
    monkeypatch.setattr(
        "packages.log_service.log_deletion._today_str",
        lambda: today.isoformat(),
    )
    _write_log_entry(log_dir, deletable, {"message": "delete me"})
    _write_log_entry(log_dir, today.isoformat(), {"message": "protected"})
    app = FastAPI()
    app.include_router(router, prefix="/api/logs")
    client = TestClient(app)

    invalid = client.delete("/api/logs/2026-02-30")
    protected = client.delete(f"/api/logs/{today.isoformat()}")
    not_found = client.delete(f"/api/logs/{missing}")
    batch = client.request(
        "DELETE",
        "/api/logs/batch",
        json={"dates": [deletable, missing, today.isoformat()]},
    )

    assert invalid.status_code == 400
    assert protected.status_code == 400
    assert (log_dir / f"{today.isoformat()}.jsonl").is_file()
    assert not_found.status_code == 200
    assert not_found.json() == {"date": missing, "deleted": False}
    assert batch.status_code == 200
    assert batch.json() == {
        "deleted": [deletable],
        "not_found": [missing],
        "protected": [today.isoformat()],
    }


def test_log_cleanup_api_obeys_cutoff_and_rejects_zero(
    tmp_path: Path, monkeypatch
) -> None:
    log_dir = tmp_path / "logs"
    today = date(2026, 7, 26)
    before_cutoff = (today - timedelta(days=8)).isoformat()
    cutoff = (today - timedelta(days=7)).isoformat()
    after_cutoff = (today - timedelta(days=6)).isoformat()
    monkeypatch.setattr(
        "packages.log_service.log_deletion.get_log_dir",
        lambda: log_dir,
    )
    monkeypatch.setattr(
        "packages.log_service.log_deletion._today_str",
        lambda: today.isoformat(),
    )
    for log_date in (before_cutoff, cutoff, after_cutoff, today.isoformat()):
        _write_log_entry(log_dir, log_date, {"message": log_date})
    app = FastAPI()
    app.include_router(router, prefix="/api/logs")
    client = TestClient(app)

    rejected = client.delete("/api/logs/cleanup?before_days=0")
    response = client.delete("/api/logs/cleanup?before_days=7")

    assert rejected.status_code == 422
    assert response.status_code == 200
    assert response.json() == {
        "deleted": [before_cutoff],
        "deleted_count": 1,
    }
    assert not (log_dir / f"{before_cutoff}.jsonl").exists()
    for retained in (cutoff, after_cutoff, today.isoformat()):
        assert (log_dir / f"{retained}.jsonl").is_file()


def test_log_dates_api_paginates_newest_first_and_keeps_requested_empty_page(
    tmp_path: Path, monkeypatch
) -> None:
    log_dir = tmp_path / "logs"
    for log_date in ("2026-07-24", "2026-07-25", "2026-07-26"):
        _write_log_entry(log_dir, log_date, {"message": log_date})
    monkeypatch.setattr(
        "packages.log_service.log_writer.user_data_dir",
        lambda *_args, **_kwargs: str(tmp_path),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/logs")
    client = TestClient(app)

    second_page = client.get("/api/logs/dates?page=2&page_size=2")
    empty_page = client.get("/api/logs/dates?page=99&page_size=2")

    assert second_page.status_code == 200
    page_payload = second_page.json()
    assert page_payload["total"] == 3
    assert page_payload["page"] == 2
    assert page_payload["page_size"] == 2
    assert len(page_payload["items"]) == 1
    assert page_payload["items"][0]["date"] == "2026-07-24"
    assert page_payload["items"][0]["error_count"] == 1
    assert page_payload["items"][0]["size_bytes"] > 0
    assert empty_page.json() == {
        "items": [],
        "total": 3,
        "page": 99,
        "page_size": 2,
    }
    assert client.get("/api/logs/dates?page=0").status_code == 422
    assert client.get("/api/logs/dates?page_size=201").status_code == 422
