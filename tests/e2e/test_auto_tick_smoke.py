"""End-to-end smoke test for AutoTickScheduler (Issue #426, parent #387).

This is intentionally NOT a unit test. The goal is to prove that when a real
control-plane process boots (``create_app`` + ``TestClient`` lifespan) the
``AutoTickScheduler`` actually runs in its event loop, scans the workspace,
dispatches a Job through the live phase-transition path, and writes the
result back to the real ``FileStoreRepository``. Unit tests
(``tests/control_plane/test_auto_tick_concurrency.py``) already cover
isolation, fairness, dedup, shutdown etc. on the class in isolation; this
test covers the *integration boundary* that issue #414 retired the deprecated
Dispatcher / WorkerLoop and the production codebase runs the new scheduler.

Acceptance criteria (mirroring issue #426):

* AutoTickScheduler heartbeat visible in logs (``[AUTO-TICK]`` log record).
* Created Job advances at least one phase (file-store record ``phase``
  leaves ``queued`` for a later phase).
* No ``Dispatcher`` / ``WorkerLoop`` / ``/workers/poll`` mentions anywhere
  in captured logs (those code paths have been deleted by issue #414).

The test does NOT call external LLM/TTS APIs. It substitutes a
``Mock(spec=JobTickService)`` whose ``tick()`` loads the JobRecord via the
real ``FileStoreRepository``, advances its ``phase`` to the next phase in
``PHASE_ORDER``, and writes it back. That is enough to prove the scheduler's
``run_pass → _execute_job → JobTickService.tick → record phase change``
chain runs end-to-end against the real ``FileStoreRepository`` without
invoking any external service.
"""

from __future__ import annotations

import logging
import re
import time as _wall_clock
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import apps.control_plane.app as app_module
from apps.control_plane.app import create_app
from packages.domain_core.models import JobRecord, PHASE_ORDER, PhaseExecutionState
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import JobTickService, TickSummary

# Regexes for deprecated surfaces retired by #414. If any of these show up
# in the captured logs the scheduler is accidentally falling through to the
# old Dispatcher / WorkerLoop path — exactly the regression #387 wants to
# prevent from sneaking back in.
_RETIRED_SURFACE_PATTERNS = (
    re.compile(r"\bDispatcher\b"),
    re.compile(r"\bWorkerLoop\b"),
    re.compile(r"/workers/poll"),
    re.compile(r"/workers/heartbeat"),
    re.compile(r"/workers/ack"),
)


def _build_smoke_tick_svc(repo: FileStoreRepository) -> JobTickService:
    """Return a Mock(spec=JobTickService) that always reports a phase advance.

    The mock mirrors the production ``JobTickService.tick()`` contract at
    the level the scheduler cares about:

    * ``tick()`` is called by the scheduler (call_count check).
    * It returns a ``TickSummary`` with ``action != "skipped"`` so the
      ``[AUTO-TICK]`` log line is emitted.
    * It also writes the new phase into the real ``FileStoreRepository``
      so the on-disk JobRecord actually transitions — this is what the
      production tick path does and is the only way the e2e assertion
      ``phase == "script_generating"`` can pass without bypassing the
      scheduler entirely.

    ``Mock(spec=JobTickService)`` enforces the public API surface —
    passing this into ``AutoTickScheduler.__init__`` would type-check
    the same way the real production wiring does.
    """
    svc = Mock(spec=JobTickService)

    def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
        # Mirror the production write-back: load → mutate → save via the
        # real repository.  Doing it here keeps the scheduler-side
        # untouched (we are not modifying production code) while still
        # giving the e2e assertion something observable on disk.
        record = repo.load_job(project_id, job_id)
        next_phase_name = PHASE_ORDER[PHASE_ORDER.index(record.phase) + 1]
        record.phase = next_phase_name  # type: ignore[assignment]
        record.execution = PhaseExecutionState(status="running", current_attempt=1)
        repo.save_job(project_id, record)
        return TickSummary(
            action="advanced",
            from_phase="queued",
            to_phase=next_phase_name,
            message="smoke-test stub",
        )

    svc.tick.side_effect = _tick
    return svc


def test_auto_tick_scheduler_runs_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Boots ``create_app`` in dev-auto-tick mode, proves a Job advances.

    Wiring diagram:

        TestClient(create_app(root_dir))
            └── lifespan: DEV_AUTO_TICK=1
                └── asyncio.create_task(_auto_tick(...))
                    └── while True: await scheduler.run_pass()
                        └── collect_candidates()  → real FileStoreRepository
                        └── _execute_job(work)
                            └── JobTickService.tick(...)  → mocked
                                → loads JobRecord, advances phase, saves
                                → returns TickSummary("advanced", "queued", <next>)
                            └── INFO "[AUTO-TICK] job-001: queued -> <next> (advanced)"
    """
    # ── Arrange ────────────────────────────────────────────────────────
    # DEV_AUTO_TICK=1 is what activates the background _auto_tick loop in
    # the lifespan. AUTO_TICK_INTERVAL=0 makes the loop run a pass as fast
    # as the asyncio scheduler allows — no sleeping — so the test does not
    # have to wait 3 s per pass.
    monkeypatch.setenv("DEV_AUTO_TICK", "1")
    monkeypatch.setenv("EXPORT_SYNC", "1")  # deterministic sync executor
    monkeypatch.setattr(app_module, "AUTO_TICK_INTERVAL", 0)

    # Materialise a real project + real JobRecord via the real repository.
    # AutoTickScheduler._collect_candidates only picks up records that
    # actually exist on disk — there is no test seam around it.
    repo = FileStoreRepository(tmp_path)
    repo.create_project("proj-smoke")
    job = JobRecord(
        job_id="job-001",
        project_id="proj-smoke",
        product="smoke_product",
        phase="queued",
        review_status="none",
        mode="generate",
    )
    repo.save_job("proj-smoke", job)

    # Inject the stub tick service via the public seam _build_default_tick_svc
    # — the same seam test_lifespan_no_pending_child_tasks uses. This is the
    # ONLY way to control what the real scheduler sees without modifying
    # production code. The stub mirrors the production tick path's
    # write-back to the file store so the e2e assertion can observe the
    # phase actually advance on disk.
    tick_svc = _build_smoke_tick_svc(repo)
    monkeypatch.setattr(
        app_module,
        "_build_default_tick_svc",
        lambda root_dir, config_reader: tick_svc,
    )

    # Capture backend logs. The "[AUTO-TICK]" record is emitted by
    # AutoTickScheduler._execute_job at INFO level on
    # ``apps.control_plane.auto_tick_scheduler``.
    caplog.set_level(logging.INFO, logger="apps.control_plane.auto_tick_scheduler")
    # log_service writes through its own handler; capture it broadly.
    caplog.set_level(logging.INFO)

    # ── Act ────────────────────────────────────────────────────────────
    app = create_app(tmp_path)
    with TestClient(app) as client:
        # Confirm the lifespan actually wired the background task — this
        # is the "scheduler is alive" assertion that distinguishes e2e
        # from a mocked unit test.
        assert app.state.auto_tick_task is not None
        assert not app.state.auto_tick_task.done()

        # Liveness probe. /api/health is defined in create_app() and does
        # not require any Job/Phase state.
        resp = client.get("/api/health")
        assert resp.status_code == 200, resp.text

        # Wait for the scheduler to dispatch at least one pass and the
        # thread offload to complete. The poll loop interval is 0, but the
        # asyncio.shield + run_in_executor path takes a few event-loop
        # turns to land. Cap the wait at a generous bound so a stuck
        # scheduler fails fast instead of hanging the suite.
        deadline = 30.0
        started = _wall_clock.monotonic()
        advanced = False
        final_phase = "queued"
        while _wall_clock.monotonic() - started < deadline:
            record = repo.load_job("proj-smoke", "job-001")
            final_phase = record.phase
            # The acceptance criterion is "at least one phase transition
            # out of 'queued'".  Because the interval is 0 and the stub
            # tick advances unconditionally, the job can race past any
            # single target phase between polls — so we check for "moved
            # off queued" rather than "equals a specific phase".
            if record.phase != "queued":
                advanced = True
                break
            # Yield to the event loop so the background task gets a turn.
            _wall_clock.sleep(0.05)

    # ── Assert: phase transition happened ──────────────────────────────
    assert advanced, (
        "AutoTickScheduler did not advance job-001 out of 'queued' within "
        f"{deadline}s — scheduler is alive in lifespan but "
        "JobTickService.tick was never dispatched, or its returned "
        "TickSummary did not persist to the file store."
    )
    # Sanity: the phase must be one of the legitimate pipeline phases,
    # not some garbage string the stub wrote.
    _VALID_PIPELINE_PHASES = set(PHASE_ORDER) | {"completed"}
    assert final_phase in _VALID_PIPELINE_PHASES, (
        f"final phase {final_phase!r} is not a known PHASE_ORDER value"
    )
    assert final_phase != "queued", (
        "advanced=True but final_phase is still 'queued' — internal "
        "consistency error in the polling loop"
    )

    # ── Assert: scheduler actually called tick() at least once ─────────
    assert tick_svc.tick.call_count >= 1, (
        f"JobTickService.tick was not invoked (call_count="
        f"{tick_svc.tick.call_count}); the scheduler scanned but did not "
        f"dispatch the job."
    )

    # ── Assert: AutoTickScheduler heartbeat is in the captured logs ────
    auto_tick_logs = [
        record
        for record in caplog.records
        if record.name == "apps.control_plane.auto_tick_scheduler"
        and "[AUTO-TICK]" in record.getMessage()
    ]
    assert auto_tick_logs, (
        "No '[AUTO-TICK]' log line was emitted by AutoTickScheduler. "
        "Captured records: "
        f"{[(r.name, r.getMessage()) for r in caplog.records]}"
    )
    # The scheduler emits "[AUTO-TICK] {job_id}: {from} -> {to} ({action})".
    # Verify that at least one such line mentions job-001 and an action
    # of "advanced" — this is the heartbeat that proves the scheduler's
    # _execute_job actually completed (and therefore tick() was invoked,
    # the TickSummary was non-skipped, and the future ran to completion).
    matching = [
        r
        for r in auto_tick_logs
        if "job-001" in r.getMessage() and "advanced" in r.getMessage()
    ]
    assert matching, (
        "Scheduler log present but no line confirmed a job-001 advance. "
        f"Got: {[r.getMessage() for r in auto_tick_logs]}"
    )

    # ── Assert: no retired Dispatcher / WorkerLoop surfaces in logs ────
    all_log_text = "\n".join(f"{r.name}|{r.getMessage()}" for r in caplog.records)
    leaked = [
        pattern.pattern
        for pattern in _RETIRED_SURFACE_PATTERNS
        if pattern.search(all_log_text)
    ]
    assert not leaked, (
        "Retired Dispatcher / WorkerLoop surface leaked into runtime logs: "
        f"{leaked}. This is a regression of issue #414 — the deprecated "
        "worker pull loop must not appear anywhere in the auto-tick path."
    )
