"""Regression harness for batch mode > 2 jobs dispatch (Issue: batch-mode-over-2-jobs).

User report
-----------
> 批量模式的时候，任务生成数量设置为 2 条视频时，生产能够正常成功；
> 一旦任务视频数量大于 2 条，生产流程就会失败。

Goal
----
Drive the **full** user pipeline — the real ``POST /api/projects/<id>/jobs/batch``
endpoint, the real ``AutoTickScheduler`` (with bounded concurrency), and the
real ``FileStoreRepository`` — under both N=2 and N=3, with the phase-orchestrator
side-effects stubbed to a deterministic in-memory model.  The assertion is the
one symptom the user actually reported:

  * When a user creates N=3 jobs in one batch call and the auto-tick scheduler
    is running, every one of the N=3 jobs MUST eventually be dispatched.
  * The same harness must pass for N=2 (the control case the user said works).

The harness deliberately does NOT attempt to lock a specific phase or status
on each job — the user's report does not name a failure mode (create-time
error? hung-in-queued? mid-pipeline crash?), only that "production fails"
when N>2.  This harness pins the *dispatchability* invariant:
**no batch-created job is silently dropped by the scheduler under
N>MAX_CONCURRENT_JOBS=2.**

Reproduction
------------
* Boot ``create_app(tmp_path)`` with ``DEV_AUTO_TICK=1`` and
  ``EXPORT_SYNC=1`` so the auto-tick loop is alive but deterministic.
* Inject a stub ``_build_default_tick_svc`` whose ``tick()`` advances the
  job to its next PHASE_ORDER phase, writes back via the real
  ``FileStoreRepository``, and returns ``TickSummary(action="advanced")``.
  This is the same shape the existing ``test_auto_tick_smoke`` uses — the
  scheduler's correctness can be tested without invoking external
  LLM/TTS/ffmpeg services.
* POST a batch of N=2 (control) and N=3 (regression) jobs through the
  real batch API.
* Run the scheduler for a fixed number of passes and assert every batch
  job's ``phase`` has left ``"queued"`` and the ``execution.status`` is
  ``"succeeded"`` (or at least the scheduler actually called
  ``JobTickService.tick`` for every job).

If this test fails, the bug is in the scheduler / batch interaction.
If it passes, the bug lives somewhere the harness does not exercise
(LLM/TTS, asset_library, runtime_adapters, or — most likely — the
production environment which this harness cannot replicate); in that
case the harness becomes the regression-test seam for whatever
subsequent root cause is identified.
"""

from __future__ import annotations

import time as _wall_clock
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import apps.control_plane.app as app_module
from apps.control_plane.app import create_app
from packages.domain_core.models import (
    PHASE_ORDER,
    PhaseExecutionState,
)
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import (
    JobTickService,
    TickSummary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_product_config(client: TestClient, tmp_path: Path) -> None:
    """Configure product default_name/brand so the batch API accepts creation."""
    resp = client.put(
        "/api/config/product",
        json={
            "default_name": "regression_product",
            "default_brand": "regression_brand",
        },
    )
    assert resp.status_code == 200, resp.text


def _create_project(client: TestClient, name: str) -> str:
    resp = client.post("/api/projects", json={"name": name})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _batch_create(client: TestClient, project_id: str, n: int) -> list[dict[str, Any]]:
    """Create *n* jobs in a single batch call.  Returns the list of result rows."""
    items = [{"name": f"批次任务 #{i + 1:02d}", "mode": "generate"} for i in range(n)]
    resp = client.post(
        f"/api/projects/{project_id}/jobs/batch",
        json={"platforms": ["douyin"], "jobs": items},
    )
    assert resp.status_code == 200, (
        f"batch create N={n} returned {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["count"] == n
    return body["results"]


def _build_advancing_tick_svc(
    repo: FileStoreRepository, *, cap_at: str | None = None
) -> JobTickService:
    """Return a JobTickService stub that advances the phase one step per tick.

    Mirrors the production tick contract: load → mutate → save.  *cap_at*
    optionally stops the phase advance at the named phase so a follow-up
    test pass can observe the post-cap state.
    """
    svc = Mock(spec=JobTickService)

    def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
        record = repo.load_job(project_id, job_id)
        current_idx = PHASE_ORDER.index(record.phase)
        # Already at terminal — return a no-op summary.
        if current_idx + 1 >= len(PHASE_ORDER):
            return TickSummary(
                action="skipped",
                from_phase=record.phase,
                to_phase=record.phase,
                message="already at terminal",
            )
        next_phase = PHASE_ORDER[current_idx + 1]
        if cap_at is not None and next_phase == cap_at:
            # Stop right before the capped phase.
            record.phase = record.phase  # type: ignore[assignment]
            record.execution = PhaseExecutionState(
                status="succeeded", current_attempt=1
            )
            repo.save_job(project_id, record)
            return TickSummary(
                action="skipped",
                from_phase=record.phase,
                to_phase=record.phase,
                message=f"capped before {cap_at}",
            )
        record.phase = next_phase  # type: ignore[assignment]
        record.execution = PhaseExecutionState(status="succeeded", current_attempt=1)
        repo.save_job(project_id, record)
        return TickSummary(
            action="advanced",
            from_phase=PHASE_ORDER[current_idx],
            to_phase=next_phase,
            message="harness stub",
        )

    svc.tick.side_effect = _tick
    return svc


def _wait_until_all_dispatched(
    tick_svc: Mock,
    expected: set[str],
    timeout: float = 15.0,
) -> None:
    """Poll until *tick_svc* has been called for every job_id in *expected*."""
    deadline = _wall_clock.monotonic() + timeout
    while _wall_clock.monotonic() < deadline:
        called = {
            (call.args[1] if len(call.args) >= 2 else None)
            for call in tick_svc.tick.call_args_list
        }
        if expected.issubset(called):
            return
        _wall_clock.sleep(0.05)
    called = {
        (call.args[1] if len(call.args) >= 2 else None)
        for call in tick_svc.tick.call_args_list
    }
    missing = expected - called
    raise AssertionError(
        f"After {timeout}s, scheduler never dispatched jobs: {sorted(missing)} "
        f"(dispatched so far: {sorted(c for c in called if c)})"
    )


# ---------------------------------------------------------------------------
# Control: N=2 must continue to work (regression guard for the working case)
# ---------------------------------------------------------------------------


def test_batch_create_two_jobs_dispatches_both(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N=2: control case the user reports still works.

    This is the *control* half of the experiment.  If this ever fails, the
    scheduler regressed for the working case as well — a louder alarm than
    the N>2 failure.
    """
    monkeypatch.setenv("DEV_AUTO_TICK", "1")
    monkeypatch.setenv("EXPORT_SYNC", "1")
    monkeypatch.setattr(app_module, "AUTO_TICK_INTERVAL", 0)

    repo = FileStoreRepository(tmp_path)
    tick_svc = _build_advancing_tick_svc(repo)
    monkeypatch.setattr(
        app_module,
        "_build_default_tick_svc",
        lambda root_dir, config_reader: tick_svc,
    )

    app = create_app(tmp_path)
    with TestClient(app) as client:
        _setup_product_config(client, tmp_path)
        project_id = _create_project(client, "proj-batch-2")
        results = _batch_create(client, project_id, n=2)
        job_ids = {r["job_id"] for r in results}
        assert len(job_ids) == 2

        # The scheduler is already running on the same thread the TestClient
        # is using.  By the time the batch API returns, the first jobs may
        # already have left 'queued' — so we only check that the job files
        # actually exist, not their pre-dispatch phase.
        for r in results:
            job_path = (
                tmp_path
                / "workspace"
                / "projects"
                / project_id
                / "control"
                / "jobs"
                / f"{r['job_id']}.json"
            )
            assert job_path.is_file(), f"job file not persisted: {job_path}"

        _wait_until_all_dispatched(tick_svc, job_ids, timeout=15.0)

    # Assertion: every N=2 job was actually dispatched at least once.
    dispatched = {
        (call.args[1] if len(call.args) >= 2 else None)
        for call in tick_svc.tick.call_args_list
    }
    missing = job_ids - dispatched
    assert not missing, (
        f"N=2 control: scheduler dropped jobs from dispatch: {sorted(missing)}. "
        f"Dispatched: {sorted(d for d in dispatched if d)}"
    )


# ---------------------------------------------------------------------------
# Regression: N=3 — the actual user-reported failure
# ---------------------------------------------------------------------------


def test_batch_create_three_jobs_dispatches_all_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N=3: the regression case.  This test is the *feedback loop*.

    The user reports: N=2 works, N=3 fails.  This harness boots the real
    app, creates 3 jobs via the real batch API, runs the real scheduler,
    and asserts all 3 jobs get dispatched.

    Failure modes the harness catches:
      * Batch API drops items when len(jobs) > 2.
      * Scheduler never picks up the 3rd job (the candidate filter rejects
        it; ``_collect_candidates`` walks the wrong project subtree; etc.).
      * Scheduler dispatches the 3rd job but something prevents
        ``JobTickService.tick`` from being called for it.
    """
    monkeypatch.setenv("DEV_AUTO_TICK", "1")
    monkeypatch.setenv("EXPORT_SYNC", "1")
    monkeypatch.setattr(app_module, "AUTO_TICK_INTERVAL", 0)

    repo = FileStoreRepository(tmp_path)
    tick_svc = _build_advancing_tick_svc(repo)
    monkeypatch.setattr(
        app_module,
        "_build_default_tick_svc",
        lambda root_dir, config_reader: tick_svc,
    )

    app = create_app(tmp_path)
    with TestClient(app) as client:
        _setup_product_config(client, tmp_path)
        project_id = _create_project(client, "proj-batch-3")
        results = _batch_create(client, project_id, n=3)
        job_ids = {r["job_id"] for r in results}
        assert len(job_ids) == 3, (
            f"batch API returned {len(job_ids)} unique job_ids, expected 3"
        )

        # The scheduler is already running on the same thread the TestClient
        # is using.  By the time the batch API returns, the first jobs may
        # already have left 'queued' — so we only check that the job files
        # actually exist, not their pre-dispatch phase.
        for r in results:
            job_path = (
                tmp_path
                / "workspace"
                / "projects"
                / project_id
                / "control"
                / "jobs"
                / f"{r['job_id']}.json"
            )
            assert job_path.is_file(), f"job file not persisted: {job_path}"

        # Drive the scheduler: run several passes so the bounded-concurrency
        # logic has a chance to free slots and pick up the queued job.
        deadline = _wall_clock.monotonic() + 20.0
        dispatched_ids: set[str] = set()
        while _wall_clock.monotonic() < deadline:
            called = {
                (call.args[1] if len(call.args) >= 2 else None)
                for call in tick_svc.tick.call_args_list
            }
            dispatched_ids = {c for c in called if c is not None}
            if job_ids.issubset(dispatched_ids):
                break
            _wall_clock.sleep(0.05)

    # ── Primary assertion: every N=3 job reached the scheduler ───────────
    missing = job_ids - dispatched_ids
    assert not missing, (
        f"N=3 REGRESSION: scheduler never dispatched {sorted(missing)}. "
        f"User reported 'N=3 fails' — this assertion is the trip-wire. "
        f"Dispatched (deduped): {sorted(dispatched_ids)}"
    )

    # ── Secondary: every job actually advanced out of 'queued' on disk ──
    for jid in job_ids:
        record = repo.load_job(project_id, jid)
        assert record.phase != "queued", (
            f"job {jid} was dispatched but phase still 'queued' on disk — "
            f"the tick side-effect did not persist a phase change"
        )


# ---------------------------------------------------------------------------
# Differential: N=5 stress — proves dispatch scales beyond N=2
# ---------------------------------------------------------------------------


def test_batch_create_five_jobs_dispatches_all_five(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N=5: amplifies the 2/3 boundary the user observed.

    If the bug is "MAX_CONCURRENT_JOBS=2 plus some interaction at N>2",
    pushing N higher makes it more likely to surface.  Same harness shape
    as N=3.
    """
    monkeypatch.setenv("DEV_AUTO_TICK", "1")
    monkeypatch.setenv("EXPORT_SYNC", "1")
    monkeypatch.setattr(app_module, "AUTO_TICK_INTERVAL", 0)

    repo = FileStoreRepository(tmp_path)
    tick_svc = _build_advancing_tick_svc(repo)
    monkeypatch.setattr(
        app_module,
        "_build_default_tick_svc",
        lambda root_dir, config_reader: tick_svc,
    )

    app = create_app(tmp_path)
    with TestClient(app) as client:
        _setup_product_config(client, tmp_path)
        project_id = _create_project(client, "proj-batch-5")
        results = _batch_create(client, project_id, n=5)
        job_ids = {r["job_id"] for r in results}
        assert len(job_ids) == 5

        _wait_until_all_dispatched(tick_svc, job_ids, timeout=20.0)

    dispatched = {
        (call.args[1] if len(call.args) >= 2 else None)
        for call in tick_svc.tick.call_args_list
    }
    missing = job_ids - dispatched
    assert not missing, (
        f"N=5 stress: scheduler dropped {sorted(missing)}. "
        f"Dispatched: {sorted(d for d in dispatched if d)}"
    )


# ---------------------------------------------------------------------------
# End-to-end timing: review-gate stop + slot release + queued job pickup
# ---------------------------------------------------------------------------


def _build_review_gated_tick_svc(
    repo: FileStoreRepository, *, stop_phase: str = "script_review"
) -> JobTickService:
    """Tick stub that advances phases one step at a time, then **stops** at *stop_phase*.

    Mirrors the production default review strategy (``review_each``) where
    a job pauses for human review at every review-gate phase.  The harness
    then asserts: once the first two jobs reach the review gate and free
    their slots, the third job — which started in ``queued`` — must be
    picked up and advanced in a later pass.

    This is the *exact* scheduling shape the user runs in production:
    3 jobs in one batch, MAX_CONCURRENT_JOBS=2, review_each default, so
    the 3rd job waits in queued and only gets a slot after the first two
    hit a review gate and stop ticking.
    """
    svc = Mock(spec=JobTickService)

    def _tick(project_id, job_id, product, *, root_dir, project_dir, options):
        record = repo.load_job(project_id, job_id)
        current_idx = PHASE_ORDER.index(record.phase)
        if current_idx + 1 >= len(PHASE_ORDER):
            return TickSummary(
                action="skipped",
                from_phase=record.phase,
                to_phase=record.phase,
                message="terminal",
            )
        next_phase = PHASE_ORDER[current_idx + 1]
        # Stop at the review gate — do not advance past it.  This mirrors
        # the production behaviour where _review_requires_human returns True
        # and the scheduler skips the job on the next pass because
        # phase in REVIEW_PHASES and review_status == "pending".
        if next_phase == stop_phase:
            record = record.model_copy(
                update={
                    "phase": next_phase,  # type: ignore[arg-type]
                    "review_status": "pending",
                    "execution": PhaseExecutionState(
                        status="succeeded", current_attempt=1
                    ),
                }
            )
            repo.save_job(project_id, record)
            return TickSummary(
                action="advanced",
                from_phase=PHASE_ORDER[current_idx],
                to_phase=next_phase,
                message=f"reached review gate {next_phase}",
            )
        # Otherwise advance to the next phase.
        record = record.model_copy(
            update={
                "phase": next_phase,  # type: ignore[arg-type]
                "execution": PhaseExecutionState(status="succeeded", current_attempt=1),
            }
        )
        repo.save_job(project_id, record)
        return TickSummary(
            action="advanced",
            from_phase=PHASE_ORDER[current_idx],
            to_phase=next_phase,
            message="harness stub",
        )

    svc.tick.side_effect = _tick
    return svc


def test_batch_three_jobs_with_review_gate_advances_all_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N=3 + review-gate stop: every job reaches the review gate eventually.

    This is the *realistic* shape of the user's batch run:

      * MAX_CONCURRENT_JOBS = 2 (default)
      * review_each strategy (default)
      * Phase order: queued → script_generating → script_review → ...

    On the first pass, jobs 1 and 2 start; job 3 stays in ``queued``.
    Jobs 1 and 2 advance to ``script_review`` and stop.  Once they stop,
    pass 2 has free slots and job 3 should run.

    The user reports this exact configuration fails.  If it does, the
    trip-wire is the assertion that all three jobs reach
    ``script_review`` (or beyond).
    """
    monkeypatch.setenv("DEV_AUTO_TICK", "1")
    monkeypatch.setenv("EXPORT_SYNC", "1")
    monkeypatch.setattr(app_module, "AUTO_TICK_INTERVAL", 0)

    repo = FileStoreRepository(tmp_path)
    tick_svc = _build_review_gated_tick_svc(repo, stop_phase="script_review")
    monkeypatch.setattr(
        app_module,
        "_build_default_tick_svc",
        lambda root_dir, config_reader: tick_svc,
    )

    app = create_app(tmp_path)
    with TestClient(app) as client:
        _setup_product_config(client, tmp_path)
        project_id = _create_project(client, "proj-batch-review")
        results = _batch_create(client, project_id, n=3)
        job_ids = {r["job_id"] for r in results}
        assert len(job_ids) == 3

        # The realistic deadline: under the stub the first 2 jobs reach the
        # review gate in 1-2 ticks, then a later pass picks up job 3.  20s
        # is generous; if it can't dispatch in that time something is wrong.
        deadline = _wall_clock.monotonic() + 20.0
        phases_at_deadline: dict[str, str] = {}
        while _wall_clock.monotonic() < deadline:
            _wall_clock.sleep(0.1)
            reached_gate = 0
            for jid in job_ids:
                try:
                    r = repo.load_job(project_id, jid)
                except (FileNotFoundError, ValueError):
                    continue
                if r.phase == "script_review":
                    reached_gate += 1
            if reached_gate == 3:
                break

        for jid in job_ids:
            try:
                phases_at_deadline[jid] = repo.load_job(project_id, jid).phase
            except (FileNotFoundError, ValueError):
                phases_at_deadline[jid] = "<unreadable>"

    # ── The user's actual trip-wire ─────────────────────────────────────
    # All 3 batch jobs must reach the review gate — which is what "production
    # succeeded" means in the user's mental model.  If job 3 is still in
    # queued / script_generating, the user's report is reproduced.
    not_at_gate = {
        jid: phase
        for jid, phase in phases_at_deadline.items()
        if phase != "script_review"
    }
    assert not not_at_gate, (
        f"Batch N=3 with review gate: not all jobs reached script_review. "
        f"Still stuck: {not_at_gate}.  All phases: {phases_at_deadline}.  "
        f"This is the user's 'N=3 fails' symptom."
    )
