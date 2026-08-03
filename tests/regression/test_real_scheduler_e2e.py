"""Real AutoTickScheduler + real JobTickService e2e, NO TestClient.

Why this exists
---------------
The user reports: batch creation succeeds for N=2, fails for N>2.
The handoff (2026-07-31) ruled out several hypotheses but had no
reproducer; this file is the **machine-verifiable** "is the
scheduler/tick chain correct for N>2" check.

Driving the real ``AutoTickScheduler.run_pass()`` directly in a real
asyncio event loop, paired with the real ``JobTickService.tick()`` chain
and stubbed phase handlers, lets us answer: **"Given the production
code path with no external LLM/TTS/ffmpeg calls, can N jobs all reach
the review gate within bounded time?"**

* If N=2, N=3, N=5 all pass → the scheduler/tick chain is correct and
  the bug lives in a layer we don't exercise here (real LLM/TTS,
  asset_library, or the user's specific configuration).
* If N>2 fails → a real bug is in the production code path; the
  diagnostic message names which jobs got stuck and at which phase.

This is *the* regression-test seam for batch mode with N>2.  It does
**not** lock a specific bug — the user's failure mode is not yet
known — but it pins the invariant the user said worked for N=2 and
extends it to N=3 and N=5.
"""

from __future__ import annotations

import asyncio
import json
import time as _wall_clock
from pathlib import Path

import pytest

import apps.control_plane.app as app_module
from apps.control_plane.app import _build_default_tick_svc
from apps.control_plane.auto_tick_scheduler import AutoTickScheduler
from packages.domain_core.models import (
    ArtifactPointer,
    JobRecord,
    PHASE_ORDER,
)
from packages.file_store.repository import FileStoreRepository
from packages.provider_config.config_reader import ConfigReader


def _write_product_config(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "product": {
            "default_name": "regression_product",
            "default_brand": "regression_brand",
        }
    }
    (config_dir / "app_config.json").write_text(
        json.dumps(cfg, ensure_ascii=False), encoding="utf-8"
    )


def _install_phase_handler_stubs(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Replace every phase handler with a tiny-artifact stub.

    Each stub returns one ``ArtifactPointer`` so the orchestrator treats
    it as a successful handler run and the ``_transition_after_artifacts``
    path advances the phase.  No external services are invoked.
    """
    counts: dict[str, int] = {}

    def _make_stub(name: str):
        def _stub(orchestrator, ctx):
            counts[name] = counts.get(name, 0) + 1
            return [
                ArtifactPointer(
                    kind=f"{name}_artifact",
                    url="",
                    relative_path="",
                    size_bytes=0,
                )
            ]

        return _stub

    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_script",
        _make_stub("script_generating"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_tts",
        _make_stub("tts_generating"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_tts_review",
        _make_stub("tts_review"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_subtitle",
        _make_stub("subtitle_generating"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_asset",
        _make_stub("asset_retrieving"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_video_rendering",
        _make_stub("video_rendering"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_final_rendering",
        _make_stub("final_rendering"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_final_review",
        _make_stub("final_review"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_scene_assembly",
        _make_stub("scene_assembling"),
    )
    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator.run_montage_assembly",
        _make_stub("montage_assembling"),
    )
    return counts


def _wait_for_phases(
    repo: FileStoreRepository,
    project_id: str,
    job_ids: set[str],
    target_phase: str,
    deadline_monotonic: float,
) -> dict[str, str]:
    later_or_equal: set[str] = set()
    for p in PHASE_ORDER:
        later_or_equal.add(p)
        if p == target_phase:
            break
    final: dict[str, str] = {}
    while _wall_clock.monotonic() < deadline_monotonic:
        ok = True
        for jid in job_ids:
            try:
                rec = repo.load_job(project_id, jid)
                final[jid] = rec.phase
                if rec.phase not in later_or_equal:
                    ok = False
            except (FileNotFoundError, ValueError):
                ok = False
        if ok:
            return final
        _wall_clock.sleep(0.02)
    return final


@pytest.mark.asyncio
@pytest.mark.parametrize("n", [2, 3, 5])
async def test_real_scheduler_real_tick_n_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, n: int
) -> None:
    """N-job batch, real AutoTickScheduler + real JobTickService.

    No TestClient.  No lifespan auto-tick.  We drive the scheduler's
    ``run_pass()`` directly in a real asyncio event loop, with a
    per-job thread that invokes ``JobTickService.tick()`` exactly as
    production does.
    """
    monkeypatch.setenv("DEV_AUTO_TICK", "0")
    monkeypatch.setattr(app_module, "AUTO_TICK_INTERVAL", 0)
    counts = _install_phase_handler_stubs(monkeypatch)

    # 1. Materialise a real workspace with product config + project.
    _write_product_config(tmp_path)
    repo = FileStoreRepository(tmp_path)
    repo.create_project("proj-real")
    project_id = "proj-real"

    # 2. Persist N jobs (mimic what the batch API does after validation).
    job_ids: set[str] = set()
    for i in range(n):
        jid = f"job_regression_product_{i:08x}"
        job_ids.add(jid)
        rec = JobRecord(
            job_id=jid,
            project_id=project_id,
            product="regression_product",
            brand="regression_brand",
            platforms=["douyin"],
            name=f"批次任务 #{i + 1:02d}",
            mode="generate",
            phase="queued",
            review_status="none",
            auto_approve=False,
            review_strategy="review_each",
            language="mandarin",
            audio_source="tts",
            skip_subtitle=False,
        )
        repo.save_job(project_id, rec)

    # 3. Build a real JobTickService from the real orchestrator.
    config_dir = tmp_path / "config"
    reader = ConfigReader(config_dir=str(config_dir))
    tick_svc = _build_default_tick_svc(tmp_path, reader)

    # 4. Build a real AutoTickScheduler pointed at the same workspace.
    scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

    # 5. Run scheduler passes directly.  Each ``run_pass`` is async;
    #    block on each pass to give the dispatched executor threads
    #    time to finish.  We do this in a tight async loop until the
    #    deadline expires.
    deadline = _wall_clock.monotonic() + 30.0
    while _wall_clock.monotonic() < deadline:
        await scheduler.run_pass()
        # Drain in-flight tasks so slots free up before the next pass.
        if scheduler._running:
            running = list(scheduler._running.values())
            await asyncio.gather(*running, return_exceptions=True)

    # 6. Final read.
    final: dict[str, str] = {}
    for jid in job_ids:
        try:
            rec = repo.load_job(project_id, jid)
            final[jid] = rec.phase
        except (FileNotFoundError, ValueError):
            final[jid] = "<unreadable>"

    await scheduler.shutdown()

    not_at_gate = {jid: ph for jid, ph in final.items() if ph != "script_review"}
    assert not not_at_gate, (
        f"N={n}: not all jobs reached script_review.  "
        f"Stuck: {not_at_gate}.  All: {final}.  handler counts={counts}"
    )
    assert counts.get("script_generating", 0) >= n, (
        f"N={n}: only {counts.get('script_generating', 0)} jobs went through "
        f"the handler — {n} were expected.  counts={counts}"
    )


@pytest.mark.asyncio
async def test_real_scheduler_n3_repeated(
    tmp_path_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """N=3 repeated: amplify the 2/3 boundary.

    The user reports the failure as reliable for N=3.  If the bug is
    probabilistic (race condition with low N), running 5 trials of
    N=3 should expose it.  If all 5 trials pass, the bug is *not* in
    the scheduler/tick chain under any concurrent pressure we can
    exercise.
    """
    trials = 5
    failures: list[str] = []

    for trial in range(trials):
        tmp_path = tmp_path_factory.mktemp(f"trial-{trial}")
        try:
            await _run_one_batch_n3(tmp_path, monkeypatch, trial)
        except AssertionError as e:
            failures.append(f"trial={trial}: {str(e)[:300]}")

    assert not failures, (
        f"N=3 repeated {trials}x: {len(failures)}/{trials} failed.  "
        f"Failures: {failures}"
    )


async def _run_one_batch_n3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trial: int
) -> None:
    """One trial of N=3 batch with real scheduler/tick."""
    # Install handler stubs for this trial.
    _install_phase_handler_stubs(monkeypatch)

    _write_product_config(tmp_path)
    repo = FileStoreRepository(tmp_path)
    repo.create_project(f"proj-trial-{trial}")
    project_id = f"proj-trial-{trial}"

    job_ids: set[str] = set()
    for i in range(3):
        jid = f"job_t_{trial}_{i:08x}"
        job_ids.add(jid)
        rec = JobRecord(
            job_id=jid,
            project_id=project_id,
            product="regression_product",
            brand="regression_brand",
            platforms=["douyin"],
            name=f"批次任务 #{i + 1:02d}",
            mode="generate",
            phase="queued",
            review_status="none",
            auto_approve=False,
            review_strategy="review_each",
            language="mandarin",
            audio_source="tts",
            skip_subtitle=False,
        )
        repo.save_job(project_id, rec)

    config_dir = tmp_path / "config"
    reader = ConfigReader(config_dir=str(config_dir))
    tick_svc = _build_default_tick_svc(tmp_path, reader)
    scheduler = AutoTickScheduler(tmp_path, tick_svc, max_concurrency=2)

    deadline = _wall_clock.monotonic() + 15.0
    while _wall_clock.monotonic() < deadline:
        await scheduler.run_pass()
        if scheduler._running:
            running = list(scheduler._running.values())
            await asyncio.gather(*running, return_exceptions=True)

    final: dict[str, str] = {}
    for jid in job_ids:
        try:
            rec = repo.load_job(project_id, jid)
            final[jid] = rec.phase
        except (FileNotFoundError, ValueError):
            final[jid] = "<unreadable>"

    await scheduler.shutdown()

    not_at_gate = {jid: ph for jid, ph in final.items() if ph != "script_review"}
    assert not not_at_gate, f"trial={trial}: N=3 stuck.  phases={final}"


async def _drive_scheduler(scheduler: AutoTickScheduler, deadline: float) -> None:
    """Drive ``run_pass`` repeatedly until the deadline."""
    while _wall_clock.monotonic() < deadline:
        try:
            await scheduler.run_pass()
        except Exception:
            pass
        # Yield to the event loop briefly.
        await asyncio.sleep(0)
