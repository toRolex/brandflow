"""Auto-tick scheduler with bounded concurrent job execution and round-robin fairness.

Replaces the serial ``_auto_tick`` inner loop with a scheduler that launches
up to ``max_concurrency`` concurrent ``asyncio.Task`` wrappers per scan
pass.  Each wrapper offloads the blocking ``JobTickService.tick()`` call to
a dedicated thread via ``run_in_executor``.

Key properties
--------------
* At most *max_concurrency* Job ticks run concurrently (default 2).
* The same ``(project_id, job_id)`` is never dispatched twice simultaneously.
* Round-robin cursor prevents fixed-sort-order starvation.
* Single-job exceptions are isolated — other slots continue unimpeded.
* ``shutdown()`` drains running tasks gracefully (no force-kill).
* File-system scanning is offloaded to a thread so it never blocks the event loop.

Thread safety
-------------
Two concurrent ``tick()`` calls share a single ``JobTickService``,
``PhaseOrchestrator``, and ``ConfigReader``.  This is safe because:

* Each job reads/writes disjoint paths: ``control/jobs/{job_id}.json``
  and ``runtime/jobs/{job_id}/``.
* ``_compute_transition`` is a documented pure function (zero I/O).
* ``PhaseOrchestrator`` has no per-call mutable state.
* ``ConfigReader`` reads are protected by a ``threading.Lock``; reloads
  build a local snapshot and swap atomically under that lock.
* ``FileStoreRepository.save_job`` uses ``os.replace`` which is atomic
  on the same volume (Windows + POSIX).
* ``FileStoreRepository.append_review_event`` serialises writes per project
  via a ``threading.Lock``.
* ``SentenceTTSService._synthesize_sentence`` uses ``tempfile + os.replace``
  to atomically publish cache entries.
* No scheduler-layer locking is needed beyond the ``_running`` dict guarded
  by the single-threaded event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from packages.domain_core.models import REVIEW_PHASES
from packages.file_store.layout import WorkspaceLayout
from packages.log_service.log_writer import log_error
from packages.pipeline_services.job_tick_service import (
    JobTickService,
    NON_TICKABLE_PHASES,
    PhaseExecutionError,
    TickSummary,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

JobKey = tuple[str, str]  # (project_id, job_id)

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _WorkItem:
    """Immutable snapshot of everything a single Job tick needs.

    Frozen so background closures cannot late-bind loop variables — every
    task receives its own copy captured at dispatch time.
    """

    project_id: str
    job_id: str
    project_dir: Path
    job_file_path: Path
    product: str
    options: tuple[tuple[str, str], ...]  # frozen key-value pairs
    review_status: str = ""

    @property
    def key(self) -> JobKey:
        return (self.project_id, self.job_id)

    def to_options_dict(self) -> dict[str, str]:
        """Reconstitute the mutable options dict when the thread needs it."""
        return dict(self.options)


# ---------------------------------------------------------------------------
# AutoTickScheduler
# ---------------------------------------------------------------------------


class AutoTickScheduler:
    """Bounded-concurrency scheduler for the auto-tick scan loop.

    Parameters
    ----------
    root_dir : Path
        Repository root (parent of ``workspace/``).
    tick_svc : JobTickService
        The tick service to invoke for each job.
    max_concurrency : int
        Maximum number of concurrent top-level Job ticks.  Must be >= 1.
    """

    def __init__(
        self,
        root_dir: Path,
        tick_svc: JobTickService,
        *,
        max_concurrency: int = 2,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError(f"max_concurrency must be >= 1, got {max_concurrency}")
        self._layout = WorkspaceLayout(root_dir)
        self._tick_svc = tick_svc
        self._max_concurrency = max_concurrency

        self._running: dict[JobKey, asyncio.Task[None]] = {}
        self._dispatch_cursor: JobKey | None = None
        self._closing = False
        self._scan_future: asyncio.Future[list[_WorkItem]] | None = None
        # Dedicated thread pool for file-system scanning so that a large
        # workspace tree never blocks the event loop.
        self._scan_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="at-scan"
        )

    # -- public API ----------------------------------------------------------

    async def run_pass(self) -> None:
        """Scan the filesystem and fill free concurrency slots.

        One call corresponds to one auto-tick cycle (every 3 s).
        Slots occupied by still-running tasks from a previous pass are
        skipped so the same Job is never dispatched twice.
        """
        if self._closing:
            return

        loop = asyncio.get_running_loop()
        scan_future = loop.run_in_executor(
            self._scan_executor, self._collect_candidates
        )
        self._scan_future = scan_future
        try:
            # Keep the underlying scan alive if run_pass() is cancelled so
            # shutdown() can retain ownership and drain it.
            candidates = await asyncio.shield(scan_future)
        finally:
            if scan_future.done() and self._scan_future is scan_future:
                self._scan_future = None

        # Re-check _closing after the (potentially long) scan so that a
        # shutdown triggered mid-scan does not race with dispatch.
        if self._closing:
            return

        free_slots = self._max_concurrency - len(self._running)
        if free_slots <= 0:
            return

        # Round-robin start: begin scanning from the position after the
        # last-dispatched job so earlier jobs don't perpetually dominate.
        start_index = self._round_robin_start(candidates)

        dispatched = 0
        n = len(candidates)
        for offset in range(n):
            idx = (start_index + offset) % n
            work = candidates[idx]
            if work.key in self._running:
                continue

            task = asyncio.create_task(
                self._execute_job(work), name=f"auto-tick-{work.job_id}"
            )
            self._running[work.key] = task
            task.add_done_callback(self._on_task_done)
            self._dispatch_cursor = work.key
            dispatched += 1
            if dispatched >= free_slots:
                break

    async def shutdown(self) -> None:
        """Gracefully stop scheduling and drain running tasks.

        After this returns:
        * No new tasks will be dispatched.
        * All previously launched wrapper tasks have completed.
        * ``_running`` is empty.
        * The scan executor is shut down regardless of whether tasks were running.
        """
        self._closing = True
        if self._scan_future is not None:
            await asyncio.gather(self._scan_future, return_exceptions=True)
            self._scan_future = None
        if self._running:
            tasks = list(self._running.values())
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Actively consume any unretrieved exceptions so they don't
            # surface as "Task exception was never retrieved" warnings.
            for result in results:
                if isinstance(result, BaseException) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    log_error(
                        {
                            "source": "backend",
                            "level": "error",
                            "message": f"Scheduler shutdown: task exception: {result}",
                            "stack_trace": traceback.format_exception(
                                type(result), result, result.__traceback__
                            ),
                        }
                    )

            self._running.clear()
        self._scan_executor.shutdown(wait=True)

    # -- internal callbacks ---------------------------------------------------

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        """Done callback: consume exception + release the JobKey.

        Using a callback is safer than ``finally`` inside the coroutine
        because it runs even when the wrapper Task is cancelled before the
        coroutine body reaches its own ``finally``.  This guarantees the
        slot is always released and the exception is always retrieved.
        """
        # Find and remove the JobKey for this task so the next scan pass
        # can re-dispatch the job.
        for key, t in list(self._running.items()):
            if t is task:
                del self._running[key]
                break

        if task.cancelled():
            return

        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is None:
            return

        # If the wrapper coroutine didn't already log it (PhaseExecutionError
        # and generic Exception are handled inside _execute_job), log it here
        # as a safety net.  Only new types that escaped _execute_job reach
        # this point.
        if not isinstance(exc, (PhaseExecutionError,)):
            log_error(
                {
                    "source": "backend",
                    "level": "error",
                    "message": f"AUTO-TICK unhandled wrapper exception: {exc}",
                    "stack_trace": traceback.format_exception(
                        type(exc), exc, exc.__traceback__
                    ),
                }
            )

    # -- internal helpers ----------------------------------------------------

    def _collect_candidates(self) -> list[_WorkItem]:
        """Scan the filesystem and return a sorted list of dispatchable jobs.

        Ordering is deterministic: projects sorted by name, then jobs within
        each project sorted by file name.

        Terminal phases and jobs waiting for human review are filtered out
        so they don't waste dispatch slots.  They naturally re-enter the
        candidate set when their phase or review_status changes (e.g. via
        the retry or review API).
        """
        # Per-field type checks for every JSON key we dereference.  A dict
        # like {"job_id":"x","phase":[]} passes isinstance(data, dict) but
        # would crash on ``phase in _SKIP_PHASES`` (TypeError: unhashable
        # type).  We validate all eight fields before any use.
        _FIELD_CHECKS: tuple[tuple[str, type], ...] = (
            ("job_id", str),
            ("phase", str),
            ("review_status", str),
            ("product", str),
            ("manual_script", str),
            ("uploaded_audio_path", str),
            ("language", str),
            ("mode", str),
        )

        candidates: list[_WorkItem] = []
        projects_root = self._layout.projects_dir()
        if not projects_root.exists():
            return candidates

        for project_dir in sorted(projects_root.iterdir()):
            if not project_dir.is_dir():
                continue
            project_id = project_dir.name
            jobs_dir = self._layout.control_jobs_dir(project_id)
            if not jobs_dir.exists():
                continue

            for job_file in sorted(jobs_dir.glob("*.json")):
                try:
                    raw_text = job_file.read_text(encoding="utf-8")
                    data = json.loads(raw_text)
                except (json.JSONDecodeError, OSError) as exc:
                    log_error(
                        {
                            "source": "backend",
                            "level": "warn",
                            "message": f"Unreadable job file skipped: {job_file} — {exc}",
                        }
                    )
                    continue

                # Guard against malformed JSON whose top-level value is not a
                # dict (null, [], string, number).  These would otherwise
                # raise AttributeError and silently abort the entire pass.
                if not isinstance(data, dict):
                    log_error(
                        {
                            "source": "backend",
                            "level": "warn",
                            "message": (
                                f"Malformed job file (top-level {type(data).__name__},"
                                f" expected dict): {job_file}"
                            ),
                        }
                    )
                    continue

                job_id_raw = data.get("job_id")
                if not isinstance(job_id_raw, str) or not job_id_raw:
                    continue
                job_id: str = job_id_raw

                # --- strict field-type guards --------------------------------
                bad = None
                for fname, ftype in _FIELD_CHECKS:
                    val = data.get(fname)
                    if val is not None and not isinstance(val, ftype):
                        bad = (fname, type(val).__name__, ftype.__name__)
                        break
                if bad is not None:
                    log_error(
                        {
                            "source": "backend",
                            "level": "warn",
                            "message": (
                                f"Bad job file: {bad[0]} is {bad[1]}"
                                f" (expected {bad[2]}) in {job_file}"
                            ),
                        }
                    )
                    continue

                phase: str = data.get("phase", "")
                review_status: str = data.get("review_status", "")

                # Skip jobs that can never be ticked forward.
                if phase in NON_TICKABLE_PHASES:
                    continue
                # Skip jobs waiting for human review — they will re-enter
                # the candidate set once the review status changes.
                if phase in REVIEW_PHASES and review_status == "pending":
                    continue

                product: str = data.get("product", os.environ.get("PRODUCT", ""))
                # Build frozen tuple so _WorkItem is genuinely immutable.
                options_list: list[tuple[str, str]] = [
                    ("manual_script", data.get("manual_script", "")),
                    ("uploaded_audio_path", data.get("uploaded_audio_path", "")),
                    ("language", data.get("language", "mandarin")),
                    ("mode", data.get("mode", "generate")),
                ]

                candidates.append(
                    _WorkItem(
                        project_id=project_id,
                        job_id=job_id,
                        project_dir=project_dir,
                        job_file_path=job_file,
                        product=product,
                        options=tuple(options_list),
                        review_status=review_status,
                    )
                )

        return candidates

    def _round_robin_start(self, candidates: list[_WorkItem]) -> int:
        """Return the index in *candidates* where scanning should begin.

        If the previous dispatch cursor points to a job that still exists
        in this pass, start one past it.  Otherwise start at 0.
        """
        if self._dispatch_cursor is None:
            return 0
        for i, work in enumerate(candidates):
            if work.key == self._dispatch_cursor:
                return (i + 1) % len(candidates)
        return 0

    async def _execute_job(self, work: _WorkItem) -> None:
        """Run one Job tick, offloaded to the thread pool.

        All exception handling is self-contained so the parent
        ``run_pass()`` never sees an unhandled task failure.

        Slot cleanup is handled by ``_on_task_done`` — not by ``finally``
        inside this coroutine — but in the cancellation path we wait for
        the thread to finish before letting the callback release the
        JobKey.  This prevents a re-dispatch from racing with the still-
        running OS thread.
        """
        executor_future = None
        try:
            loop = asyncio.get_running_loop()

            def _tick_job() -> TickSummary:
                svc = self._tick_svc
                return svc.tick(
                    work.project_id,
                    work.job_id,
                    work.product,
                    root_dir=self._layout.root,
                    project_dir=work.project_dir,
                    options=work.to_options_dict(),
                )

            executor_future = loop.run_in_executor(None, _tick_job)
            # Shield so that cancellation of *this* wrapper Task does NOT
            # propagate into the executor (which cannot cancel an OS
            # thread).  The thread always runs to completion or crashes
            # on its own.
            summary = await asyncio.shield(executor_future)
            if summary.action != "skipped":
                _logger.info(
                    "[AUTO-TICK] %s: %s -> %s (%s)",
                    work.job_id,
                    summary.from_phase,
                    summary.to_phase,
                    summary.action,
                )
        except asyncio.CancelledError:
            # The wrapper was cancelled, but the OS thread is still running.
            # Wait for the thread to finish so the same Job can't be
            # re-dispatched while this thread is still touching its files.
            if executor_future is not None:
                try:
                    await executor_future
                except Exception:
                    pass  # already logged by the normal exception path
            raise
        except PhaseExecutionError as e:
            log_error(
                {
                    "source": "backend",
                    "level": "error",
                    "message": f"{e.phase} phase failed: {e}",
                    "extra": {"job_id": e.job_id, "phase": e.phase},
                    "stack_trace": traceback.format_exc(),
                }
            )
        except Exception as e:
            log_error(
                {
                    "source": "backend",
                    "level": "error",
                    "message": f"AUTO-TICK {work.job_file_path.name}: {e}",
                    "extra": {"job_file": work.job_file_path.name},
                    "stack_trace": traceback.format_exc(),
                }
            )
