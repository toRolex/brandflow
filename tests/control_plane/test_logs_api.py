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

    assert client.post(
        "/api/logs/error",
        json={"source": "frontend", "level": "error", "message": "boom"},
    ).json() == {"ok": True}
    date = next((tmp_path / "logs").glob("*.jsonl")).stem
    assert client.get("/api/logs/dates").json()[0]["error_count"] == 1
    response = client.get(f"/api/logs/download?date={date}")
    assert response.status_code == 200
    assert json.loads(response.text)["message"] == "boom"
