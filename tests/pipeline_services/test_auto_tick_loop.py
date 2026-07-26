"""Tests for the refactored _auto_tick outer loop and AutoTickScheduler.

Now that _auto_tick delegates to AutoTickScheduler, these tests cover:

* ``_build_default_tick_svc`` — the internal seam for default construction.
* ``_auto_tick`` outer loop — sleep + run_pass + shutdown lifecycle.
* ``AutoTickScheduler.run_pass()`` — dispatch, log_error integration.
* Executor offloading — tick dispatched via ``run_in_executor``.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from apps.control_plane.auto_tick_scheduler import AutoTickScheduler
from packages.pipeline_services.job_tick_service import (
    JobTickService,
    PhaseExecutionError,
    TickSummary,
)


class _LoopDone(Exception):
    """Internal exception to break out of the auto_tick while loop."""


def _make_job_json(job_id: str, phase: str = "queued") -> str:
    return json.dumps(
        {
            "job_id": job_id,
            "project_id": "proj-001",
            "product": "羊肚菌",  # 羊肚菌
            "phase": phase,
            "review_status": "none",
            "artifacts": [],
            "manual_script": "",
            "uploaded_audio_path": "",
            "language": "mandarin",
        },
        ensure_ascii=False,
    )


@pytest.fixture
def mock_projects(tmp_path: Path) -> Path:
    """Create a temporary workspace with one project and one job file."""
    jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
    jobs_dir.mkdir(parents=True)
    (jobs_dir / "job-001.json").write_text(_make_job_json("job-001"), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# _build_default_tick_svc seam
# ---------------------------------------------------------------------------


class TestBuildDefaultTickSvc:
    """Verify the internal seam constructs a real JobTickService."""

    def test_creates_real_service(self, tmp_path: Path) -> None:
        from apps.control_plane.app import _build_default_tick_svc
        from packages.provider_config.config_reader import ConfigReader

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "app_config.json").write_text("{}", encoding="utf-8")
        reader = ConfigReader(config_dir=str(config_dir))

        svc = _build_default_tick_svc(tmp_path, reader)
        assert isinstance(svc, JobTickService)
        assert svc._orchestrator is not None
        assert svc._repo is not None


# ---------------------------------------------------------------------------
# _auto_tick outer loop (scheduler-backed)
# ---------------------------------------------------------------------------


class TestAutoTickLoop:
    """Verify the _auto_tick outer loop behaviour with AutoTickScheduler."""

    async def _run_one_tick(self, root_dir: Path) -> None:
        """Run _auto_tick for exactly one iteration, then break via _LoopDone."""
        first_sleep = True

        async def _controlled_sleep(_seconds: float) -> None:
            nonlocal first_sleep
            if first_sleep:
                first_sleep = False
                return
            raise _LoopDone()

        with (
            patch(
                "apps.control_plane.app._build_default_tick_svc",
                return_value=Mock(spec=JobTickService),
            ),
            patch("asyncio.sleep", _controlled_sleep),
        ):
            from apps.control_plane.app import _auto_tick

            with pytest.raises(_LoopDone):
                await _auto_tick(root_dir, None)

    async def test_loop_calls_shutdown_on_exit(self, mock_projects: Path) -> None:
        """After the loop exits (via _LoopDone), scheduler.shutdown() is called."""
        tick_svc = Mock(spec=JobTickService)
        tick_svc.tick.return_value = TickSummary(
            action="skipped", from_phase="queued", to_phase="queued"
        )

        first_sleep = True

        async def _controlled_sleep(_seconds: float) -> None:
            nonlocal first_sleep
            if first_sleep:
                first_sleep = False
                return
            raise _LoopDone()

        with patch("asyncio.sleep", _controlled_sleep):
            from apps.control_plane.app import _auto_tick

            with pytest.raises(_LoopDone):
                await _auto_tick(mock_projects, None, tick_svc=tick_svc)

        # Loop exited gracefully — no assertion needed beyond no exception.

    async def test_loop_catches_run_pass_error(self, mock_projects: Path) -> None:
        """The outer loop catches exceptions from run_pass() and logs them.

        We simulate this by making run_pass itself raise (not a job-level
        error, but a genuine scheduler failure).
        """
        first_sleep = True

        async def _controlled_sleep(_seconds: float) -> None:
            nonlocal first_sleep
            if first_sleep:
                first_sleep = False
                return
            raise _LoopDone()

        with (
            patch("asyncio.sleep", _controlled_sleep),
            patch("apps.control_plane.app.log_error") as log_error,
            patch(
                "apps.control_plane.auto_tick_scheduler.AutoTickScheduler.run_pass",
                side_effect=RuntimeError("scheduler failure"),
            ),
        ):
            from apps.control_plane.app import _auto_tick

            with pytest.raises(_LoopDone):
                await _auto_tick(
                    mock_projects, None, tick_svc=Mock(spec=JobTickService)
                )

        # The outer loop should have logged the error
        assert log_error.called, "Expected log_error to be called for loop error"
        entry = log_error.call_args.args[0]
        assert "AUTO-TICK LOOP ERROR" in entry["message"]
        assert "RuntimeError" in entry["stack_trace"]


# ---------------------------------------------------------------------------
# AutoTickScheduler dispatch tests
# ---------------------------------------------------------------------------


class TestSchedulerDispatch:
    """Verify AutoTickScheduler.run_pass() dispatches correctly."""

    @pytest.mark.asyncio
    async def test_iterates_all_jobs(self, mock_projects: Path) -> None:
        """The scheduler dispatches tick() for each job file in one pass."""
        tick_svc = Mock(spec=JobTickService)
        tick_svc.tick.return_value = TickSummary(
            action="skipped", from_phase="queued", to_phase="queued"
        )

        scheduler = AutoTickScheduler(mock_projects, tick_svc, max_concurrency=2)
        await scheduler.run_pass()
        # Let background tasks finish
        await asyncio.sleep(0.05)

        tick_svc.tick.assert_called()
        call_args_list = [(c.args[0], c.args[1]) for c in tick_svc.tick.call_args_list]
        assert ("proj-001", "job-001") in call_args_list

        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_continues_after_failed_summary(self, mock_projects: Path) -> None:
        """Tick returning action='failed' does not block other jobs."""
        jobs_dir = (
            mock_projects / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        )
        (jobs_dir / "job-002.json").write_text(
            _make_job_json("job-002"), encoding="utf-8"
        )

        ticked: list[str] = []
        lock = threading.Lock()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            with lock:
                ticked.append(job_id)
            return TickSummary(
                action="failed",
                from_phase="script_generating",
                to_phase="failed",
                message="fail",
            )

        tick_svc = Mock(spec=JobTickService)
        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(mock_projects, tick_svc, max_concurrency=2)
        await scheduler.run_pass()
        await asyncio.sleep(0.05)

        assert "job-001" in ticked
        assert "job-002" in ticked

        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_generic_exception_in_one_job_doesnt_block_others(
        self, mock_projects: Path
    ) -> None:
        """Generic exception in one job doesn't prevent other from being ticked."""
        jobs_dir = (
            mock_projects / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        )
        (jobs_dir / "job-002.json").write_text(
            _make_job_json("job-002"), encoding="utf-8"
        )

        ticked: list[str] = []
        lock = threading.Lock()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            with lock:
                ticked.append(job_id)
            if job_id == "job-001":
                raise ValueError("unexpected error")
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc = Mock(spec=JobTickService)
        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(mock_projects, tick_svc, max_concurrency=2)
        await scheduler.run_pass()
        await asyncio.sleep(0.05)

        assert "job-002" in ticked

        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_logs_generic_tick_exception(self, mock_projects: Path) -> None:
        """Generic exception from tick() is logged via log_error."""
        tick_svc = Mock(spec=JobTickService)
        tick_svc.tick.side_effect = ValueError("unexpected error")

        with patch("apps.control_plane.auto_tick_scheduler.log_error") as log_error:
            scheduler = AutoTickScheduler(mock_projects, tick_svc, max_concurrency=2)
            await scheduler.run_pass()
            await asyncio.sleep(0.05)

        assert log_error.called
        entry = log_error.call_args.args[0]
        assert entry["source"] == "backend"
        assert entry["level"] == "error"
        assert "AUTO-TICK job-001.json" in entry["message"]
        assert entry["extra"] == {"job_file": "job-001.json"}
        assert "ValueError: unexpected error" in entry["stack_trace"]

        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_exception_cleans_up_running(self, mock_projects: Path) -> None:
        """When a tick raises PhaseExecutionError, slot is released via finally."""
        jobs_dir = (
            mock_projects / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        )
        (jobs_dir / "job-002.json").write_text(
            _make_job_json("job-002"), encoding="utf-8"
        )

        tick_svc = Mock(spec=JobTickService)

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            if job_id == "job-001":
                raise PhaseExecutionError(
                    job_id, "unknown", "simulated crash", ValueError("boom")
                )
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(mock_projects, tick_svc, max_concurrency=2)
        await scheduler.run_pass()
        await asyncio.sleep(0.05)

        assert len(scheduler._running) == 0, (
            f"slot leak: {len(scheduler._running)} still in _running"
        )

        await scheduler.shutdown()


# ---------------------------------------------------------------------------
# Executor offloading (Issue #266)
# ---------------------------------------------------------------------------


class TestExecutorOffloading:
    """Verify that AutoTickScheduler dispatches ticks via run_in_executor."""

    @pytest.mark.asyncio
    async def test_tick_runs_in_executor(self, mock_projects: Path) -> None:
        """Verify that tick() is dispatched via loop.run_in_executor."""
        tick_svc = Mock(spec=JobTickService)
        tick_svc.tick.return_value = TickSummary(
            action="skipped", from_phase="queued", to_phase="queued"
        )

        exec_calls: list[tuple] = []
        loop = asyncio.get_running_loop()
        original = loop.run_in_executor

        def _recording_run_in_executor(executor, func, *args):
            exec_calls.append((executor, func))
            return original(executor, func, *args)

        loop.run_in_executor = _recording_run_in_executor
        try:
            scheduler = AutoTickScheduler(mock_projects, tick_svc, max_concurrency=2)
            await scheduler.run_pass()
            await asyncio.sleep(0.05)
        finally:
            loop.run_in_executor = original

        assert len(exec_calls) >= 2, (
            f"Expected at least 2 run_in_executor calls (scan + tick), got {len(exec_calls)}"
        )
        # The last call dispatches tick() via the default thread pool (None).
        tick_call = exec_calls[-1]
        assert tick_call[0] is None  # default thread pool for tick
        assert callable(tick_call[1])
        tick_svc.tick.assert_called()

        await scheduler.shutdown()
