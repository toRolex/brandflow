"""Tests for the refactored _auto_tick outer loop."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock, patch


import pytest

from packages.pipeline_services.job_tick_service import (
    JobTickService,
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
