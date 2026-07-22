from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def test_lifespan_reclaims_background_task_and_export_executor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Production-style background resources must not outlive a TestClient."""
    monkeypatch.setenv("DEV_AUTO_TICK", "1")
    monkeypatch.setenv("EXPORT_SYNC", "0")
    app = create_app(tmp_path)
    executor = app.state.export_executor

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        auto_tick_task = app.state.auto_tick_task
        assert not auto_tick_task.done()
        assert executor.submit(lambda: None).result(timeout=1) is None

    assert auto_tick_task.cancelled()
    with pytest.raises(RuntimeError, match="cannot schedule new futures"):
        executor.submit(lambda: None)
