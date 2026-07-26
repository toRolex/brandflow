"""Tests for AutoTickScheduler concurrent job execution (Issue #352).

Synchronisation strategy
------------------------
Most handler threads signal arrival via per-job ``threading.Event``
objects, then block on a shared ``hold`` event.  The real-repository
isolation case uses a ``threading.Barrier`` to prove both reads overlap.
Blocking waits are never performed on the event-loop thread.
"""

from __future__ import annotations

import asyncio
import json
import threading
import warnings
from pathlib import Path
from unittest.mock import Mock

import pytest

from apps.control_plane.auto_tick_scheduler import AutoTickScheduler
from packages.domain_core.models import JobRecord
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import (
    JobTickService,
    PhaseExecutionError,
    TickSummary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job_json(
    job_id: str,
    project_id: str = "proj-001",
    phase: str = "queued",
    product: str = "test_product",
    mode: str = "generate",
) -> str:
    return json.dumps(
        {
            "job_id": job_id,
            "project_id": project_id,
            "product": product,
            "phase": phase,
            "review_status": "none",
            "artifacts": [],
            "manual_script": "",
            "uploaded_audio_path": "",
            "language": "mandarin",
            "mode": mode,
        },
        ensure_ascii=False,
    )


def _create_job_file(
    jobs_dir: Path,
    job_id: str,
    project_id: str = "proj-001",
    phase: str = "queued",
    product: str = "test_product",
    mode: str = "generate",
) -> Path:
    jobs_dir.mkdir(parents=True, exist_ok=True)
    path = jobs_dir / f"{job_id}.json"
    path.write_text(
        _make_job_json(job_id, project_id, phase=phase, product=product, mode=mode),
        encoding="utf-8",
    )
    return path


def _make_tick_svc(**kwargs) -> Mock:
    svc = Mock(spec=JobTickService)
    svc.tick.return_value = kwargs.pop(
        "return_value",
        TickSummary(action="skipped", from_phase="queued", to_phase="queued"),
    )
    if "side_effect" in kwargs:
        svc.tick.side_effect = kwargs["side_effect"]
    return svc


async def _wait_event(e: threading.Event) -> None:
    """Offload a blocking ``Event.wait()`` to the default thread pool."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, e.wait)


async def _wait_for_dispatched_jobs(scheduler: AutoTickScheduler) -> None:
    """Wait for the finite batch launched by the preceding run_pass()."""
    tasks = tuple(scheduler._running.values())
    if tasks:
        await asyncio.gather(*tasks)


def _held_handler(  # noqa: D401
    arrived: threading.Event,
    hold: threading.Event,
    *,
    record_fn=None,
    record=None,
    lock=None,
) -> callable:
    """Return a tick side-effect that signals *arrived*, then blocks on *hold*.

    When *record_fn* and *record* and *lock* are all provided the handler
    records ``(project_id, job_id)`` under the lock before waiting.
    """

    def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
        if record_fn is not None and record is not None and lock is not None:
            record_fn(lock, record, project_id, job_id, product, options)
        arrived.set()
        hold.wait(timeout=10)
        return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

    return _tick


# ---------------------------------------------------------------------------
# 1. Max concurrency
# ---------------------------------------------------------------------------


class TestMaxConcurrency:
    @pytest.mark.asyncio
    async def test_max_active_never_exceeds_two(self, tmp_path: Path) -> None:
        """Three jobs, two slots — at most 2 run concurrently.

        Holds both dispatched handlers so the assertion fires while they
        are definitely both still in-flight.
        """
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        for jid in ("job-001", "job-002", "job-003"):
            _create_job_file(jobs_dir, jid)

        tick_svc = _make_tick_svc()
        hold = threading.Event()
        arrived_001 = threading.Event()
        arrived_002 = threading.Event()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            ev = arrived_001 if job_id == "job-001" else arrived_002
            ev.set()
            hold.wait(timeout=10)
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        pass_task = asyncio.create_task(scheduler.run_pass())

        # Wait for BOTH handlers to arrive (offloaded — event loop stays free)
        await _wait_event(arrived_001)
        await _wait_event(arrived_002)

        # Now both are held on hold — check assertions
        assert len(scheduler._running) == 2, (
            f"_running size={len(scheduler._running)}, expected 2"
        )
        assert ("proj-001", "job-003") not in scheduler._running

        hold.set()
        await pass_task
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_slow_job_does_not_block_other_slots(self, tmp_path: Path) -> None:
        """A slow job in one slot doesn't prevent the other slot from being used."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        for jid in ("job-001", "job-002", "job-003"):
            _create_job_file(jobs_dir, jid)

        tick_svc = _make_tick_svc()
        slow_arrived = threading.Event()
        slow_hold = threading.Event()
        fast_done = threading.Event()
        ticked: list[str] = []
        lock = threading.Lock()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            with lock:
                ticked.append(job_id)
            if job_id == "job-001":
                slow_arrived.set()
                slow_hold.wait(timeout=10)
            else:
                fast_done.set()
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        pass_task = asyncio.create_task(scheduler.run_pass())

        # Wait for the fast job to finish
        await _wait_event(fast_done)
        assert slow_arrived.is_set(), "slow job (job-001) was not dispatched"
        assert "job-001" in ticked
        assert "job-002" in ticked

        slow_hold.set()
        await pass_task
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_waiting_job_picked_up_next_pass(self, tmp_path: Path) -> None:
        """Slot freed → waiting job picked up in next pass."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        for jid in ("job-001", "job-002", "job-003"):
            _create_job_file(jobs_dir, jid)

        tick_svc = _make_tick_svc()
        slow_arrived = threading.Event()
        slow_hold = threading.Event()
        slow_done = threading.Event()
        fast_done = threading.Event()

        def _tick_pass1(project_id, job_id, product, *, root_dir, project_dir, options):
            if job_id == "job-001":
                slow_arrived.set()
                slow_hold.wait(timeout=10)
                slow_done.set()
            else:
                fast_done.set()
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick_pass1

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        # Pass 1: job-001 blocks, job-002 completes quickly
        pass1 = asyncio.create_task(scheduler.run_pass())
        await _wait_event(fast_done)
        slow_hold.set()
        await pass1

        await _wait_event(slow_done)
        await _wait_for_dispatched_jobs(scheduler)
        assert len(scheduler._running) == 0

        # Pass 2: job-003 should be picked up
        pass2_ticked: list[str] = []
        lock2 = threading.Lock()
        waiting_job_done = threading.Event()

        def _tick_pass2(project_id, job_id, product, *, root_dir, project_dir, options):
            with lock2:
                pass2_ticked.append(job_id)
            if job_id == "job-003":
                waiting_job_done.set()
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick_pass2
        await scheduler.run_pass()
        await _wait_event(waiting_job_done)
        await scheduler.shutdown()

        assert "job-003" in pass2_ticked, (
            f"job-003 never ticked; pass2_ticked={pass2_ticked}"
        )


# ---------------------------------------------------------------------------
# 2. Exception isolation
# ---------------------------------------------------------------------------


class TestExceptionIsolation:
    @pytest.mark.asyncio
    async def test_exception_isolated_and_slot_not_leaked(self, tmp_path: Path) -> None:
        """job-001 throws PhaseExecutionError, job-002 completes, both slots freed."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "job-001")
        _create_job_file(jobs_dir, "job-002")

        tick_svc = _make_tick_svc()
        ticked: list[str] = []
        lock = threading.Lock()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            with lock:
                ticked.append(job_id)
            if job_id == "job-001":
                raise PhaseExecutionError(
                    job_id, "script_generating", "simulated", ValueError("boom")
                )
            return TickSummary(
                action="advanced", from_phase="queued", to_phase="script_generating"
            )

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        await scheduler.run_pass()
        await scheduler.shutdown()

        assert "job-001" in ticked
        assert "job-002" in ticked
        assert len(scheduler._running) == 0, (
            f"slot leak: {len(scheduler._running)} still running"
        )

    @pytest.mark.asyncio
    async def test_generic_exception_isolated(self, tmp_path: Path) -> None:
        """Generic exception in one job doesn't affect the other."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "job-001")
        _create_job_file(jobs_dir, "job-002")

        tick_svc = _make_tick_svc()
        ticked: list[str] = []

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            ticked.append(job_id)
            if job_id == "job-001":
                raise ValueError("generic crash")
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        await scheduler.run_pass()
        await scheduler.shutdown()

        assert "job-001" in ticked
        assert "job-002" in ticked
        assert len(scheduler._running) == 0


# ---------------------------------------------------------------------------
# 3. JobKey dedup
# ---------------------------------------------------------------------------


class TestJobKeyDedup:
    @pytest.mark.asyncio
    async def test_same_job_key_not_concurrent_in_one_pass(
        self, tmp_path: Path
    ) -> None:
        """Same (project_id, job_id) never dispatched twice in one pass."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "job-001")
        _create_job_file(jobs_dir, "job-002")

        tick_svc = _make_tick_svc()
        hold = threading.Event()
        arrived = {jid: threading.Event() for jid in ("job-001", "job-002")}
        ticked: list[str] = []
        lock = threading.Lock()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            with lock:
                ticked.append(job_id)
            if job_id in arrived:
                arrived[job_id].set()
            hold.wait(timeout=10)
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        # Pass 1: dispatch both, hold them
        pass1 = asyncio.create_task(scheduler.run_pass())
        await _wait_event(arrived["job-001"])
        await _wait_event(arrived["job-002"])

        # job-001 should appear at most once in this pass
        count_001 = ticked.count("job-001")
        assert count_001 <= 1, (
            f"job-001 ticked {count_001} times in pass 1, expected <= 1"
        )

        # Pass 2 while both are still held: neither should be dispatched
        ticked_before = len(ticked)
        await scheduler.run_pass()
        assert len(ticked) == ticked_before, (
            f"pass 2 dispatched {len(ticked) - ticked_before} jobs while pass 1 held"
        )

        # Release and drain
        hold.set()
        await pass1
        await scheduler.shutdown()

    @pytest.mark.asyncio
    async def test_different_project_same_job_id_ok(self, tmp_path: Path) -> None:
        """Different projects with same job_id can both run."""
        jobs_a = tmp_path / "workspace" / "projects" / "proj-a" / "control" / "jobs"
        jobs_b = tmp_path / "workspace" / "projects" / "proj-b" / "control" / "jobs"
        _create_job_file(jobs_a, "job-001", project_id="proj-a")
        _create_job_file(jobs_b, "job-001", project_id="proj-b")

        tick_svc = _make_tick_svc()
        hold = threading.Event()
        arrived_a = threading.Event()
        arrived_b = threading.Event()
        ticked: list[tuple[str, str]] = []
        lock = threading.Lock()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            with lock:
                ticked.append((project_id, job_id))
            if project_id == "proj-a":
                arrived_a.set()
            else:
                arrived_b.set()
            hold.wait(timeout=10)
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        pass_task = asyncio.create_task(scheduler.run_pass())
        await _wait_event(arrived_a)
        await _wait_event(arrived_b)

        keys = set(ticked)
        assert ("proj-a", "job-001") in keys
        assert ("proj-b", "job-001") in keys

        hold.set()
        await pass_task
        await scheduler.shutdown()


# ---------------------------------------------------------------------------
# 4. Round-robin fairness
# ---------------------------------------------------------------------------


class TestRoundRobinFairness:
    @pytest.mark.asyncio
    async def test_round_robin_fairness(self, tmp_path: Path) -> None:
        """3 always-runnable jobs, 2 slots — all 3 get executed across passes."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        for jid in ("job-001", "job-002", "job-003"):
            _create_job_file(jobs_dir, jid)

        tick_svc = _make_tick_svc()
        ticked: list[str] = []
        lock = threading.Lock()
        pass_done = threading.Event()
        completed_this_pass = 0

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            nonlocal completed_this_pass
            with lock:
                ticked.append(job_id)
                completed_this_pass += 1
                if completed_this_pass == 2:
                    pass_done.set()
            return TickSummary(
                action="advanced",
                from_phase="queued",
                to_phase="script_generating",
            )

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        for _ in range(5):
            await scheduler.run_pass()
            await _wait_event(pass_done)
            await _wait_for_dispatched_jobs(scheduler)
            with lock:
                completed_this_pass = 0
                pass_done.clear()

        unique = set(ticked)
        assert "job-001" in unique, f"job-001 starved: {ticked}"
        assert "job-002" in unique, f"job-002 starved: {ticked}"
        assert "job-003" in unique, f"job-003 starved: {ticked}"

        await scheduler.shutdown()


# ---------------------------------------------------------------------------
# 5. Late-binding prevention
# ---------------------------------------------------------------------------


class TestLateBinding:
    @pytest.mark.asyncio
    async def test_each_task_receives_correct_params(self, tmp_path: Path) -> None:
        """Each background task receives its own project/job/options."""
        jobs_a = tmp_path / "workspace" / "projects" / "proj-a" / "control" / "jobs"
        jobs_b = tmp_path / "workspace" / "projects" / "proj-b" / "control" / "jobs"
        _create_job_file(
            jobs_a,
            "job-001",
            project_id="proj-a",
            product="product_a",
            mode="import",
        )
        _create_job_file(
            jobs_b,
            "job-002",
            project_id="proj-b",
            product="product_b",
            mode="generate",
        )

        tick_svc = _make_tick_svc()
        recorded: list[dict] = []
        lock = threading.Lock()
        hold = threading.Event()
        arrived_a = threading.Event()
        arrived_b = threading.Event()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            with lock:
                recorded.append(
                    {
                        "project_id": project_id,
                        "job_id": job_id,
                        "product": product,
                        "options": dict(options),
                    }
                )
            if job_id == "job-001":
                arrived_a.set()
            else:
                arrived_b.set()
            hold.wait(timeout=10)
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        pass_task = asyncio.create_task(scheduler.run_pass())
        await _wait_event(arrived_a)
        await _wait_event(arrived_b)

        proj_a = [r for r in recorded if r["job_id"] == "job-001"]
        proj_b = [r for r in recorded if r["job_id"] == "job-002"]
        assert len(proj_a) == 1
        assert len(proj_b) == 1
        assert proj_a[0]["project_id"] == "proj-a"
        assert proj_a[0]["product"] == "product_a"
        assert proj_a[0]["options"]["mode"] == "import"
        assert proj_b[0]["project_id"] == "proj-b"
        assert proj_b[0]["product"] == "product_b"
        assert proj_b[0]["options"]["mode"] == "generate"

        hold.set()
        await pass_task
        await scheduler.shutdown()


# ---------------------------------------------------------------------------
# 6. max_concurrency validation
# ---------------------------------------------------------------------------


class TestMaxConcurrencyValidation:
    @pytest.mark.asyncio
    async def test_max_concurrency_one(self, tmp_path: Path) -> None:
        """max_concurrency=1 — at most 1 job runs per pass."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        for jid in ("job-001", "job-002"):
            _create_job_file(jobs_dir, jid)

        tick_svc = _make_tick_svc()
        active = 0
        peak = 0
        lock = threading.Lock()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            with lock:
                active -= 1
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=1)
        await scheduler.run_pass()
        await scheduler.shutdown()

        assert peak <= 1, f"peak={peak} with concurrency=1"

    def test_max_concurrency_zero_or_negative_rejected(self, tmp_path: Path) -> None:
        tick_svc = _make_tick_svc()
        with pytest.raises(ValueError, match="max_concurrency"):
            AutoTickScheduler(tmp_path, tick_svc, max_concurrency=0)
        with pytest.raises(ValueError, match="max_concurrency"):
            AutoTickScheduler(tmp_path, tick_svc, max_concurrency=-1)


# ---------------------------------------------------------------------------
# 7. Dispatch eligibility
# ---------------------------------------------------------------------------


class TestDispatchEligibility:
    @pytest.mark.asyncio
    async def test_draft_jobs_do_not_consume_slots_needed_by_queued_job(
        self, tmp_path: Path
    ) -> None:
        """Draft Jobs remain inert until the enqueue API moves them to queued."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "draft-001", phase="draft")
        _create_job_file(jobs_dir, "draft-002", phase="draft")
        _create_job_file(jobs_dir, "queued-001", phase="queued")

        tick_svc = _make_tick_svc()
        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        await scheduler.run_pass()
        await scheduler.shutdown()

        assert [call.args[1] for call in tick_svc.tick.call_args_list] == ["queued-001"]


# ---------------------------------------------------------------------------
# 8. Graceful file disappearance
# ---------------------------------------------------------------------------


class TestFileDisappears:
    @pytest.mark.asyncio
    async def test_job_file_disappears_gracefully(self, tmp_path: Path) -> None:
        """Job whose file is gone between scan and tick doesn't crash the pass."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        vanished = _create_job_file(jobs_dir, "job-001")
        _create_job_file(jobs_dir, "job-002")

        tick_svc = _make_tick_svc()
        ticked: list[str] = []

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            (project_dir / "control" / "jobs" / f"{job_id}.json").read_text(
                encoding="utf-8"
            )
            ticked.append(job_id)
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        collect_candidates = scheduler._collect_candidates

        def _collect_then_delete():
            candidates = collect_candidates()
            vanished.unlink()
            return candidates

        scheduler._collect_candidates = _collect_then_delete
        await scheduler.run_pass()
        await scheduler.shutdown()

        assert ticked == ["job-002"]
        assert len(scheduler._running) == 0


# ---------------------------------------------------------------------------
# 9. Shutdown semantics
# ---------------------------------------------------------------------------


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_waits_for_in_flight_scan(self, tmp_path: Path) -> None:
        """shutdown() does not return while its filesystem scan still runs."""
        tick_svc = _make_tick_svc()
        scan_started = threading.Event()
        release_scan = threading.Event()

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        def _blocking_scan():
            scan_started.set()
            release_scan.wait(timeout=10)
            return []

        scheduler._collect_candidates = _blocking_scan
        pass_task = asyncio.create_task(scheduler.run_pass())
        await _wait_event(scan_started)

        shutdown_task = asyncio.create_task(scheduler.shutdown())
        await asyncio.sleep(0)

        assert not shutdown_task.done(), (
            "shutdown returned while scan thread was active"
        )

        release_scan.set()
        await pass_task
        await shutdown_task

    @pytest.mark.asyncio
    async def test_shutdown_waits_for_running_tasks(self, tmp_path: Path) -> None:
        """shutdown() waits for running handlers to finish."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "job-001")

        tick_svc = _make_tick_svc()
        started = threading.Event()
        finished = threading.Event()
        can_finish = threading.Event()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            started.set()
            can_finish.wait(timeout=10)
            finished.set()
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        pass_task = asyncio.create_task(scheduler.run_pass())
        await _wait_event(started)

        shutdown_task = asyncio.create_task(scheduler.shutdown())
        await asyncio.sleep(0)

        assert not shutdown_task.done(), "shutdown returned before handler finished"
        assert not finished.is_set()

        can_finish.set()
        await shutdown_task
        assert finished.is_set()

        assert len(scheduler._running) == 0
        assert scheduler._closing is True

        await pass_task

    @pytest.mark.asyncio
    async def test_shutdown_prevents_new_dispatch(self, tmp_path: Path) -> None:
        """After shutdown, run_pass() is a no-op."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "job-001")

        tick_svc = _make_tick_svc()

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        await scheduler.shutdown()

        await scheduler.run_pass()
        assert len(scheduler._running) == 0

    @pytest.mark.asyncio
    async def test_no_pending_child_tasks_after_shutdown(self, tmp_path: Path) -> None:
        """After shutdown(), no scheduler child tasks remain pending."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "job-001")

        tick_svc = _make_tick_svc()
        started = threading.Event()
        go = threading.Event()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            started.set()
            go.wait(timeout=10)
            return TickSummary(action="skipped", from_phase="queued", to_phase="queued")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        tasks_before = {t for t in asyncio.all_tasks() if not t.done()}

        pass_task = asyncio.create_task(scheduler.run_pass())
        await _wait_event(started)

        go.set()
        await scheduler.shutdown()
        await pass_task

        tasks_after = {t for t in asyncio.all_tasks() if not t.done()}
        scheduler_tasks = tasks_after - tasks_before
        scheduler_named = [
            t for t in scheduler_tasks if "auto-tick" in (t.get_name() or "")
        ]
        assert len(scheduler_named) == 0, f"Orphaned auto-tick tasks: {scheduler_named}"

    @pytest.mark.asyncio
    async def test_task_exceptions_consumed_not_unretrieved(
        self, tmp_path: Path
    ) -> None:
        """Task exceptions during shutdown don't produce 'never retrieved' warnings."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "job-001")

        tick_svc = _make_tick_svc()
        started = threading.Event()
        go = threading.Event()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            started.set()
            go.wait(timeout=10)
            raise ValueError("late crash during shutdown")

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

        pass_task = asyncio.create_task(scheduler.run_pass())
        await _wait_event(started)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            go.set()
            await scheduler.shutdown()

        task_exc_warnings = [
            x for x in w if "never retrieved" in str(x.message).lower()
        ]
        assert len(task_exc_warnings) == 0, (
            f"Unretrieved exception warnings: {task_exc_warnings}"
        )

        await pass_task

    @pytest.mark.asyncio
    async def test_cancelled_error_handled_gracefully(self, tmp_path: Path) -> None:
        """CancelledError in a task is not treated as a job failure."""
        jobs_dir = tmp_path / "workspace" / "projects" / "proj-001" / "control" / "jobs"
        _create_job_file(jobs_dir, "job-001")

        tick_svc = _make_tick_svc()

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            raise asyncio.CancelledError()

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        await scheduler.run_pass()
        await scheduler.shutdown()
        assert len(scheduler._running) == 0


# ---------------------------------------------------------------------------
# 10. Cross-job isolation (real FileStoreRepository)
# ---------------------------------------------------------------------------


class TestCrossJobIsolation:
    @pytest.mark.asyncio
    async def test_cross_job_isolation_with_real_repo(self, tmp_path: Path) -> None:
        """Concurrent ticks persist only to their own real Job records."""
        repo = FileStoreRepository(tmp_path)
        for proj_id in ("proj-a", "proj-b"):
            repo.create_project(proj_id)
            repo.save_job(
                proj_id,
                JobRecord(
                    job_id="job-001",
                    project_id=proj_id,
                    product="test_product",
                    phase="queued",
                    review_status="none",
                    mode="generate",
                ),
            )

        tick_svc = _make_tick_svc()
        both_loaded = threading.Barrier(2)

        def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
            record = repo.load_job(project_id, job_id)
            both_loaded.wait(timeout=10)
            repo.save_job(
                project_id,
                record.model_copy(update={"name": f"updated-{project_id}"}),
            )
            return TickSummary(
                action="advanced", from_phase="queued", to_phase="queued"
            )

        tick_svc.tick.side_effect = _tick

        scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)
        await scheduler.run_pass()
        await scheduler.shutdown()

        assert repo.load_job("proj-a", "job-001").name == "updated-proj-a"
        assert repo.load_job("proj-b", "job-001").name == "updated-proj-b"
