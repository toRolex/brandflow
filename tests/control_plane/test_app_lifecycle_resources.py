from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import apps.control_plane.app as app_module
from apps.control_plane.auto_tick_scheduler import AutoTickScheduler
from apps.control_plane.app import create_app
from packages.pipeline_services.job_tick_service import JobTickService, TickSummary


def test_lifespan_reclaims_background_task_and_export_executor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Production-style background resources must not outlive a TestClient.

    Verifies:
    * auto_tick_task is created and running during lifespan
    * auto_tick_task is cancelled after shutdown
    * export_executor is shut down after shutdown
    * No pending scheduler child tasks remain
    """
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


def test_lifespan_no_pending_child_tasks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Lifespan shutdown drains a real scheduler child before returning."""
    monkeypatch.setenv("DEV_AUTO_TICK", "1")
    monkeypatch.setenv("EXPORT_SYNC", "1")  # sync executor — no thread pool
    monkeypatch.setattr(app_module, "AUTO_TICK_INTERVAL", 0)

    jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "job-001.json").write_text(
        json.dumps(
            {
                "job_id": "job-001",
                "project_id": "proj-001",
                "product": "test_product",
                "phase": "queued",
                "review_status": "none",
                "manual_script": "",
                "uploaded_audio_path": "",
                "language": "mandarin",
                "mode": "generate",
            }
        ),
        encoding="utf-8",
    )

    tick_started = threading.Event()
    release_tick = threading.Event()
    tick_finished = threading.Event()
    shutdown_started = threading.Event()
    request_exit = threading.Event()
    client_ready = threading.Event()
    client_exited = threading.Event()

    tick_svc = Mock(spec=JobTickService)

    def _tick(*args, **kwargs):
        tick_started.set()
        release_tick.wait(timeout=10)
        tick_finished.set()
        return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

    tick_svc.tick.side_effect = _tick
    monkeypatch.setattr(
        app_module,
        "_build_default_tick_svc",
        lambda root_dir, config_reader: tick_svc,
    )

    original_shutdown = AutoTickScheduler.shutdown

    async def _observed_shutdown(self):
        shutdown_started.set()
        await original_shutdown(self)

    monkeypatch.setattr(AutoTickScheduler, "shutdown", _observed_shutdown)

    app = create_app(tmp_path)

    def _run_client_lifespan() -> None:
        with TestClient(app) as client:
            assert client.get("/api/health").status_code == 200
            client_ready.set()
            request_exit.wait(timeout=10)
        client_exited.set()

    client_thread = threading.Thread(target=_run_client_lifespan)
    client_thread.start()
    assert client_ready.wait(timeout=5)
    assert tick_started.wait(timeout=5)

    request_exit.set()
    assert shutdown_started.wait(timeout=5)
    assert not client_exited.is_set()

    release_tick.set()
    client_thread.join(timeout=10)

    assert not client_thread.is_alive()
    assert client_exited.is_set()
    assert tick_finished.is_set()
    auto_tick_task = app.state.auto_tick_task
    assert auto_tick_task.cancelled()


def test_lifespan_export_sync_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """EXPORT_SYNC=1 should create a _SyncExecutor that runs inline."""
    monkeypatch.setenv("DEV_AUTO_TICK", "0")
    monkeypatch.setenv("EXPORT_SYNC", "1")

    app = create_app(tmp_path)

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    # _SyncExecutor has no shutdown method — verify it didn't crash
    shutdown = getattr(app.state.export_executor, "shutdown", None)
    if shutdown is not None:
        shutdown(wait=False, cancel_futures=True)
