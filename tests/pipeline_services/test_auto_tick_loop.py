"""Tests for the refactored _auto_tick outer loop."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock, patch


import pytest

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
            "product": "羊肚菌",
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


def _patch_deps():
    """Return patchers for all expensive constructors in _auto_tick."""
    return [
        patch(
            "apps.control_plane.app.create_orchestrator",
            return_value=Mock(spec=["run_phase"]),
        ),
        patch("apps.control_plane.app.FileStoreRepository"),
    ]


class TestAutoTickLoop:
    """Verify the _auto_tick outer loop behaviour."""

    async def _run_one_tick(self, root_dir: Path) -> None:
        """Run _auto_tick for exactly one iteration of the while loop.

        Patches asyncio.sleep so the first call completes normally and the
        second call raises _LoopDone to break out of the loop.
        """
        first_sleep = True

        async def _controlled_sleep(_seconds: float) -> None:
            nonlocal first_sleep
            if first_sleep:
                first_sleep = False
                return
            raise _LoopDone()

        patchers = _patch_deps()
        for p in patchers:
            p.start()

        try:
            with patch("asyncio.sleep", _controlled_sleep):
                from apps.control_plane.app import _auto_tick

                with pytest.raises(_LoopDone):
                    await _auto_tick(root_dir, None)
        finally:
            for p in patchers:
                p.stop()

    @patch("apps.control_plane.app.JobTickService")
    async def test_iterates_all_jobs(
        self, mock_svc_cls: Mock, mock_projects: Path
    ) -> None:
        """The loop should call tick() for each job file."""
        mock_svc = Mock(spec=JobTickService)
        mock_svc.tick.return_value = TickSummary(
            action="skipped", from_phase="queued", to_phase="queued"
        )
        mock_svc_cls.return_value = mock_svc

        await self._run_one_tick(mock_projects)

        mock_svc.tick.assert_called_once()
        args = mock_svc.tick.call_args.args
        assert args[0] == "proj-001"  # project_id (positional)
        assert args[1] == "job-001"  # job_id (positional)

    @patch("apps.control_plane.app.JobTickService")
    async def test_continues_after_failed_summary(
        self, mock_svc_cls: Mock, mock_projects: Path
    ) -> None:
        """Tick returning action='failed' should be caught, loop continues to next job."""
        call_count = 0

        def _tick_side_effect(*_a, **_kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return TickSummary(
                    action="failed",
                    from_phase="script_generating",
                    to_phase="failed",
                    message="script_generating: fail",
                )
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        mock_svc = Mock(spec=JobTickService)
        mock_svc.tick.side_effect = _tick_side_effect
        mock_svc_cls.return_value = mock_svc

        jobs_dir = (
            mock_projects / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        )
        (jobs_dir / "job-002.json").write_text(
            _make_job_json("job-002"), encoding="utf-8"
        )

        await self._run_one_tick(mock_projects)

        assert call_count == 2

    @patch("apps.control_plane.app.JobTickService")
    async def test_catches_generic_exception(
        self, mock_svc_cls: Mock, mock_projects: Path
    ) -> None:
        """Generic exception should be caught, loop continues."""
        call_count = 0

        def _tick_side_effect(*_a, **_kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("unexpected error")
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        mock_svc = Mock(spec=JobTickService)
        mock_svc.tick.side_effect = _tick_side_effect
        mock_svc_cls.return_value = mock_svc

        jobs_dir = (
            mock_projects / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        )
        (jobs_dir / "job-002.json").write_text(
            _make_job_json("job-002"), encoding="utf-8"
        )

        await self._run_one_tick(mock_projects)

        assert call_count == 2


# ---------------------------------------------------------------------------
# Executor offloading + single-in-flight (Issue #266)
# ---------------------------------------------------------------------------


class TestExecutorOffloading:
    """Verify that _auto_tick dispatches ticks via run_in_executor and the
    single-in-flight guard works correctly."""

    async def _run_one_tick_with_executor_patch(
        self, root_dir: Path, wrap_fn
    ) -> None:
        """Like _run_one_tick, but with a wrapper around run_in_executor on the
        concrete event loop instance obtained via get_running_loop()."""
        first_sleep = True

        async def _controlled_sleep(_seconds: float) -> None:
            nonlocal first_sleep
            if first_sleep:
                first_sleep = False
                return
            raise _LoopDone()

        patchers = _patch_deps()
        for p in patchers:
            p.start()

        try:
            with patch("asyncio.sleep", _controlled_sleep):
                from apps.control_plane.app import _auto_tick

                # Wrap the concrete loop's run_in_executor at the instance level.
                loop = asyncio.get_running_loop()
                original = loop.run_in_executor

                async def _wrapped_run(executor, func, *args):
                    return await wrap_fn(original, executor, func, *args)

                loop.run_in_executor = _wrapped_run
                try:
                    with pytest.raises(_LoopDone):
                        await _auto_tick(root_dir, None)
                finally:
                    loop.run_in_executor = original
        finally:
            for p in patchers:
                p.stop()

    @patch("apps.control_plane.app.JobTickService")
    async def test_tick_runs_in_executor(
        self, mock_svc_cls: Mock, mock_projects: Path
    ) -> None:
        """Verify that tick() is dispatched via loop.run_in_executor."""
        mock_svc = Mock(spec=JobTickService)
        mock_svc.tick.return_value = TickSummary(
            action="skipped", from_phase="queued", to_phase="queued"
        )
        mock_svc_cls.return_value = mock_svc

        exec_calls: list[tuple] = []

        async def _recording_run_in_executor(self, executor, func, *args):
            exec_calls.append((executor, func))
            # Execute the function synchronously so the loop continues.
            return func()

        await self._run_one_tick_with_executor_patch(
            mock_projects, _recording_run_in_executor
        )

        # run_in_executor should have been called for each job.
        assert len(exec_calls) >= 1, (
            f"Expected at least 1 run_in_executor call, got {len(exec_calls)}"
        )
        # executor=None (default thread pool)
        assert exec_calls[0][0] is None
        # The second argument should be a callable (the tick closure).
        assert callable(exec_calls[0][1])
        # The tick service tick() should have been called.
        mock_svc.tick.assert_called_once()

    @patch("apps.control_plane.app.JobTickService")
    async def test_single_in_flight_guard_does_not_block_normal_flow(
        self, mock_svc_cls: Mock, mock_projects: Path
    ) -> None:
        """Verify that the _in_flight guard does not interfere with normal
        sequential job processing — both jobs are ticked."""
        jobs_dir = (
            mock_projects / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        )
        (jobs_dir / "job-002.json").write_text(
            _make_job_json("job-002"), encoding="utf-8"
        )

        ticked: list[str] = []
        mock_svc = Mock(spec=JobTickService)

        def _tick(*args, **kwargs):
            ticked.append(args[1])  # args[1] is job_id
            return TickSummary(
                action="skipped", from_phase="queued", to_phase="queued"
            )

        mock_svc.tick.side_effect = _tick
        mock_svc_cls.return_value = mock_svc

        async def _sync_run_in_executor(self, executor, func, *args):
            return func()

        await self._run_one_tick_with_executor_patch(
            mock_projects, _sync_run_in_executor
        )

        # Both jobs should have been ticked exactly once each.
        assert set(ticked) == {"job-001", "job-002"}, (
            f"Expected both jobs ticked, got {ticked}"
        )

    @patch("apps.control_plane.app.JobTickService")
    async def test_single_in_flight_guard_cleans_up_on_exception(
        self, mock_svc_cls: Mock, mock_projects: Path
    ) -> None:
        """When a tick raises an exception, the finally block cleans up
        _in_flight so subsequent jobs are still processed."""
        jobs_dir = (
            mock_projects / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        )
        (jobs_dir / "job-002.json").write_text(
            _make_job_json("job-002"), encoding="utf-8"
        )

        ticked: list[str] = []
        mock_svc = Mock(spec=JobTickService)

        def _tick(*args, **kwargs):
            ticked.append(args[1])
            if args[1] == "job-001":
                raise PhaseExecutionError(
                    args[1], "unknown", "simulated crash", ValueError("boom")
                )
            return TickSummary(
                action="skipped", from_phase="queued", to_phase="queued"
            )

        mock_svc.tick.side_effect = _tick
        mock_svc_cls.return_value = mock_svc

        async def _sync_run_in_executor(self, executor, func, *args):
            try:
                return func()
            except Exception:
                raise

        await self._run_one_tick_with_executor_patch(
            mock_projects, _sync_run_in_executor
        )

        # job-001 crashed but job-002 should still be processed
        # (finally block cleaned up _in_flight).
        assert "job-002" in ticked, (
            f"Expected job-002 to be ticked after job-001 crashed, got {ticked}"
        )
