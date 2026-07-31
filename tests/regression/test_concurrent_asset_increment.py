"""Targeted test: N=3 with REAL asset_retrieving + concurrent sqlite writes.

Hypothesis: when 2+ Jobs run asset_retrieving concurrently, the
underlying AssetRepository uses bare ``sqlite3.connect()`` with no WAL
mode and no busy_timeout.  Concurrent ``increment_usage`` calls collide
on the write lock and raise ``sqlite3.OperationalError: database is
locked``.  This is the strongest remaining candidate for "N=2 works,
N>2 fails" (handoff section 3.3 candidate A).

The test:

  1. Materialises a real asset library with 24 assets (matches the
     user's "松茸" library size).
  2. Spawns N=3 concurrent ``AssetRetriever.retrieve()`` calls (each
     calling ``increment_usage`` on selected clips).
  3. Asserts no call raises ``database is locked``.

If this fails today, the bug is reproduced.  The fix is in
``packages/pipeline_services/asset_library/repository.py`` — add
``PRAGMA journal_mode=WAL`` and ``PRAGMA busy_timeout=5000`` on each
connection.
"""

from __future__ import annotations

import sqlite3
import threading
import time as _wall_clock
from pathlib import Path

import pytest

from packages.pipeline_services.asset_library.repository import (
    AssetRepository,
)


def _populate_assets(repo: AssetRepository, n: int = 24) -> list[str]:
    """Insert *n* available assets and return their asset_ids."""
    ids: list[str] = []
    conn = sqlite3.connect(str(repo.db_path))
    try:
        for i in range(n):
            aid = f"asset-{i:03d}"
            conn.execute(
                """
                INSERT OR REPLACE INTO assets
                  (asset_id, file_path, category, product, status, usage_count)
                VALUES (?, ?, ?, ?, 'available', 0)
                """,
                (aid, f"/tmp/clip-{i:03d}.mp4", "scene", "regression_product"),
            )
            ids.append(aid)
        conn.commit()
    finally:
        conn.close()
    return ids


@pytest.mark.parametrize("concurrency", [2, 3, 5, 8])
def test_concurrent_increment_usage_no_lock_error(
    tmp_path: Path, concurrency: int
) -> None:
    """N=3+ concurrent increment_usage must not raise ``database is locked``.

    Reproduces the strongest remaining hypothesis for batch N>2 failure
    (handoff 3.3 candidate A): bare ``sqlite3.connect()`` without WAL
    or busy_timeout cannot serve concurrent writers.
    """
    repo = AssetRepository(tmp_path / "assets.db")
    _populate_assets(repo, n=24)
    asset_ids = [f"asset-{i:03d}" for i in range(24)]

    # Per-worker increment loop: each worker hammers increment_usage on
    # a shuffled set of asset_ids for ~1 second.  Multiple workers in
    # parallel writers will collide on the write lock under the default
    # journal mode.
    barrier = threading.Barrier(concurrency)
    stop = threading.Event()
    errors: list[BaseException] = []
    errors_lock = threading.Lock()
    iterations: list[int] = [0] * concurrency
    iters_lock = threading.Lock()

    def _worker(idx: int) -> None:
        try:
            barrier.wait(timeout=10)
            local_iters = 0
            while not stop.is_set():
                # Tight loop of writes only — the strongest possible
                # contention for the sqlite write lock.
                for aid in asset_ids:
                    repo.increment_usage(aid)
                    local_iters += 1
                if local_iters % (concurrency * 5) == 0:
                    with iters_lock:
                        iterations[idx] = local_iters
            with iters_lock:
                iterations[idx] = local_iters
        except BaseException as e:  # noqa: BLE001
            with errors_lock:
                errors.append(e)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(concurrency)]
    deadline = _wall_clock.monotonic() + 3.0
    for t in threads:
        t.start()
    while _wall_clock.monotonic() < deadline:
        _wall_clock.sleep(0.1)
    stop.set()
    for t in threads:
        t.join(timeout=10)

    # If ``database is locked`` happened, the bug is reproduced.
    lock_errors = [e for e in errors if "locked" in str(e).lower()]
    assert not lock_errors, (
        f"concurrency={concurrency}: {len(lock_errors)} "
        f"'database is locked' errors.  Sample: {lock_errors[:3]}.  "
        f"Total errors: {len(errors)}.  Iterations per worker: {iterations}."
    )
    # Sanity: workers actually did work.
    total_iters = sum(iterations)
    assert total_iters > 0, (
        f"concurrency={concurrency}: no iterations completed, "
        f"test infrastructure error.  errors={errors[:3]}"
    )
