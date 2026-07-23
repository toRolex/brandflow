"""Pure-function state machine for job phase transitions.

Defines types (TickAction, TickSummary, PhaseExecutionError) and the pure
transition function _compute_transition that decides what should happen next
given a JobRecord and the artifacts produced by the current phase handler.

This module has zero I/O and zero side effects — all transition logic is
contained in a single referentially transparent function.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from packages.domain_core.models import (
    ArtifactPointer,
    ExecutionFailure,
    JobRecord,
    PhaseExecutionState,
)
from packages.domain_core.phase_execution import (
    PhaseExecutionFailure,
    PhaseExecutionSuccess,
)
from packages.domain_core.models import PHASE_ORDER, REVIEW_PHASES, next_phase
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.asset_snapshot import (
    AssetValidationError,
    validate_assets,
    write_reviewed_snapshot,
)
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
    STRUCTURED_MEDIA_PHASES,
)

if TYPE_CHECKING:
    from packages.provider_config.config_reader import ConfigReader

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HANDLED_PHASES: frozenset[str] = frozenset(
    {
        "script_generating",
        "tts_generating",
        "tts_review",
        "subtitle_generating",
        "asset_retrieving",
        "montage_assembling",
        "video_rendering",
        "final_rendering",
    }
)

_TERMINAL_PHASES: frozenset[str] = frozenset(
    {"draft", "completed", "failed", "cancelled", "paused"}
)

_BACKOFF_DELAYS: tuple[float, ...] = (2.0, 4.0, 8.0)
_FAST_OUTPUT_REVIEW_PHASES: frozenset[str] = frozenset(
    {"script_review", "tts_review", "asset_review", "final_review"}
)


def _review_requires_human(record: JobRecord, phase: str) -> bool:
    """Return whether *phase* must stop for a human under this Job's policy.

    ``auto_approve`` is retained for old persisted records; its compatible
    meaning is the new, deliberately narrower ``fast_output`` strategy.
    """
    strategy = "fast_output" if record.auto_approve else record.review_strategy
    return not (strategy == "fast_output" and phase in _FAST_OUTPUT_REVIEW_PHASES)


def _retry_delay(current_attempt: int) -> float:
    """Return the backoff delay before retry attempt *current_attempt*.

    ``current_attempt`` is 1-indexed for the first retry.  The sequence is
    2/4/8 s; longer budgets reuse the last value.
    """
    index = max(0, current_attempt - 1)
    if index >= len(_BACKOFF_DELAYS):
        return _BACKOFF_DELAYS[-1]
    return _BACKOFF_DELAYS[index]


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class TickAction:
    """Pure-data description of what should happen next for a job.

    Fields
    ------
    new_phase : str | None
        The phase to transition into (None = stay in current phase).
    new_review_status : str | None
        New review status to set after the transition (None = unchanged).
    run_handler : bool
        True when the caller should execute the phase handler.
    handler_phase : str | None
        Which phase handler to run (only meaningful when *run_handler* is
        True).  ``None`` means the current phase.
    parallel_phases : list[str]
        Additional phase handlers to run in parallel with *handler_phase*
        (import-mode dual dispatch).
    review_event : dict | None
        Optional review event payload to persist when the transition is
        the result of an auto-approve.
    message : str
        Human-readable description of the decision.
    """

    new_phase: str | None = None
    new_review_status: str | None = None
    run_handler: bool = False
    handler_phase: str | None = None
    parallel_phases: list[str] = field(default_factory=list)
    review_event: dict | None = None
    message: str = ""


@dataclass
class TickSummary:
    """Public result returned to callers of the tick workflow."""

    action: str  # "skipped" | "advanced" | "completed" | "failed"
    from_phase: str
    to_phase: str
    message: str = ""


class PhaseExecutionError(Exception):
    """Raised when a phase handler fails with an unexpected error."""

    def __init__(self, job_id: str, phase: str, message: str, cause: Exception):
        self.job_id = job_id
        self.phase = phase
        self.cause = cause
        super().__init__(f"[{job_id}] {phase}: {message}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_next(phase: str) -> str:
    """Return the next phase after *phase*, or ``"completed"`` if already at the end.

    The import-only phases (``scene_assembling``, ``montage_assembling``) are
    stored after ``"completed"`` in PHASE_ORDER, so we explicitly stop the
    linear advance at ``"completed"``.
    """
    try:
        next_p = next_phase(phase)
        completed_index = PHASE_ORDER.index("completed")
        if PHASE_ORDER.index(next_p) > completed_index:
            return "completed"
        return next_p
    except ValueError:
        return "completed"


# ---------------------------------------------------------------------------
# Transition helpers (shared between tick and advance_after_report)
# ---------------------------------------------------------------------------


def _merge_artifacts(
    existing: list[ArtifactPointer],
    new_artifacts: list[ArtifactPointer],
) -> list[ArtifactPointer]:
    """Merge new artifacts into existing, replacing same-kind entries so
    re-rendered outputs (url, size_bytes, relative_path) stay current."""
    by_kind: dict[str, ArtifactPointer] = {}
    for a in existing:
        by_kind[a.kind] = a
    for a in new_artifacts:
        by_kind[a.kind] = a
    # Preserve original order for kinds that existed before; append new kinds at the end.
    result: list[ArtifactPointer] = []
    seen: set[str] = set()
    for a in existing:
        replacement = by_kind.get(a.kind)
        if replacement is not None and a.kind not in seen:
            result.append(replacement)
            seen.add(a.kind)
    for a in new_artifacts:
        if a.kind not in seen:
            result.append(a)
            seen.add(a.kind)
    return result


def _build_tick_summary(
    initial_phase: str,
    action: TickAction,
) -> TickSummary:
    """Build a TickSummary from the initial phase and the action taken."""
    to_phase = action.new_phase if action.new_phase is not None else initial_phase
    if to_phase == initial_phase:
        action_type = "skipped"
    elif to_phase == "completed":
        action_type = "completed"
    elif to_phase == "failed":
        action_type = "failed"
    else:
        action_type = "advanced"

    return TickSummary(
        action=action_type,
        from_phase=initial_phase,
        to_phase=to_phase,
        message=action.message,
    )


# ---------------------------------------------------------------------------
# Pure transition function
# ---------------------------------------------------------------------------


def _compute_transition(
    record: JobRecord,
    artifacts: tuple[Any, ...],
) -> TickAction:
    """Pure function: decides what to do next given current state.

    No I/O, no side effects.  Returns a :class:`TickAction` describing the
    transition.

    Parameters
    ----------
    record : JobRecord
        The current job state.
    artifacts : tuple
        The artifacts produced by the phase handler.  An empty tuple
        means either (a) the handler has not been invoked yet, or (b)
        the handler ran but produced no artifacts — the function
        encodes the distinction implicitly via per-phase rules.
    """
    phase = record.phase

    # Lifecycle requests take effect only at this safe transition boundary.
    # The current handler is never force-cancelled; once it returns, Tick
    # persists this terminal/paused state instead of entering another phase.
    if record.cancellation_requested:
        return TickAction(new_phase="cancelled", message="cancellation requested")
    if record.pause_requested:
        return TickAction(new_phase="paused", message="pause requested")

    # ------------------------------------------------------------------
    # 1. Terminal states — nothing to do
    # ------------------------------------------------------------------
    if phase in _TERMINAL_PHASES:
        return TickAction()

    # ------------------------------------------------------------------
    # 0b. Import mode: skip script_review/tts_review (defensive)
    # ------------------------------------------------------------------
    if record.mode == "import" and phase in ("script_review", "tts_review"):
        return TickAction(
            new_phase=_safe_next(phase),
            message=f"skip {phase} in import mode",
        )

    # ------------------------------------------------------------------
    # 1b. Import mode phase routing
    # ------------------------------------------------------------------
    if phase == "scene_assembling":
        # Do not re-run TTS when a valid tts_audio artifact already exists
        # (e.g. scene_assembling failed and was retried after TTS succeeded).
        has_tts_audio = any(a.kind == "tts_audio" for a in record.artifacts)
        if has_tts_audio:
            return TickAction(
                run_handler=True,
                handler_phase="scene_assembling",
                new_phase="subtitle_generating",
                message="scene_assembling → subtitle_generating (tts_audio already present)",
            )
        return TickAction(
            run_handler=True,
            handler_phase="scene_assembling",
            parallel_phases=["tts_generating"],
            new_phase="subtitle_generating",
            message="scene_assembling + tts_generating (parallel) → subtitle_generating",
        )

    # ------------------------------------------------------------------
    # 2. Review phases
    # ------------------------------------------------------------------
    if phase in REVIEW_PHASES:
        # 2a. Already approved → advance, reset review_status
        if record.review_status == "approved":
            return TickAction(
                new_phase=_safe_next(phase),
                new_review_status="none",
                message=f"advanced past approved review {phase}",
            )

        # 2b. Auto-approve — approve without waiting for human
        if not _review_requires_human(record, phase) and record.review_status not in (
            "approved",
            "pending",
        ):
            next_p = _safe_next(phase)
            # Chain through subtitle_generating in the same tick to close
            # the race window where a worker could grab the job before
            # the next auto_tick cycle checks skip_subtitle.
            if next_p == "subtitle_generating" and record.skip_subtitle:
                next_p = _safe_next(next_p)

            if phase in HANDLED_PHASES:
                return TickAction(
                    run_handler=True,
                    handler_phase=phase,
                    new_phase=next_p,
                    new_review_status="approved",
                    review_event={"event": "auto_approve"},
                    message=f"auto-approve {phase} → {next_p} (has handler)",
                )
            return TickAction(
                new_phase=next_p,
                new_review_status="approved",
                message=f"auto-approve {phase} → {next_p} (no handler)",
            )

        # 2c. Waiting for human review
        return TickAction(message=f"waiting for human review on {phase}")

    # ------------------------------------------------------------------
    # 3. Subtitle skip — jump over subtitle_generating
    # ------------------------------------------------------------------
    if phase == "subtitle_generating" and record.skip_subtitle:
        return TickAction(
            new_phase=_safe_next(phase),
            message="skip subtitle_generating",
        )

    # ------------------------------------------------------------------
    # 3.5. Recovery: legacy migration_required jobs → auto-recover into pipeline
    # ------------------------------------------------------------------
    if phase == "migration_required":
        if record.mode == "import":
            has_tts_audio = any(a.kind == "tts_audio" for a in record.artifacts)
            if has_tts_audio:
                return TickAction(
                    new_phase="subtitle_generating",
                    message="migration_required → subtitle_generating (auto-recovery, tts_audio present)",
                )
            return TickAction(
                run_handler=True,
                handler_phase="tts_generating",
                new_phase="subtitle_generating",
                message="migration_required → tts_generating (auto-recovery, no scene folders)",
            )
        return TickAction(
            new_phase="queued",
            message="migration_required → queued (recovery, unknown mode)",
        )

    # ------------------------------------------------------------------
    # 4. Queued → route to script_generating or import pipeline
    # ------------------------------------------------------------------
    if phase == "queued":
        if record.mode == "import":
            if not record.scene_folder_ids:
                # No scene folders configured → skip scene_assembling entirely.
                # video_rendering will use montage_segment.mp4 directly as base.mp4
                # when scene_segment.mp4 is absent.
                has_tts_audio = any(a.kind == "tts_audio" for a in record.artifacts)
                if has_tts_audio:
                    return TickAction(
                        new_phase="subtitle_generating",
                        message="queued → subtitle_generating (import, no scene folders, tts_audio present)",
                    )
                return TickAction(
                    run_handler=True,
                    handler_phase="tts_generating",
                    new_phase="subtitle_generating",
                    message="queued → tts_generating (import, no scene folders → skip scene_assembling)",
                )
            return TickAction(
                new_phase="scene_assembling",
                message="queued → scene_assembling (import mode)",
            )
        return TickAction(
            run_handler=True,
            handler_phase="script_generating",
            message="queued → script_generating",
        )

    # ------------------------------------------------------------------
    # 5. Post-handler: artifacts present or phase has no handler
    #    → delegate to per-phase failure / advance logic
    # ------------------------------------------------------------------
    if artifacts or phase not in HANDLED_PHASES:
        return _transition_after_artifacts(record, artifacts)

    # ------------------------------------------------------------------
    # 6. Pre-handler: no artifacts yet, phase has a registered handler
    #    → tell the caller to run the handler
    # ------------------------------------------------------------------
    return TickAction(
        run_handler=True,
        handler_phase=phase,
        message=f"phase {phase} needs handler execution",
    )


def _transition_after_artifacts(
    record: JobRecord,
    artifacts: tuple[Any, ...],
    *,
    phase: str | None = None,
) -> TickAction:
    """Decide transition after a phase handler produced artifacts (or not).

    Separated from ``_compute_transition`` so per-phase failure logic is
    isolated for testing.

    Parameters
    ----------
    record : JobRecord
        The current job state.
    artifacts : tuple
        Artifacts produced by the handler.
    phase : str or None
        Explicit phase to use for transition logic.  When None, uses
        ``record.phase``.  This eliminates the ``temp_record.model_copy``
        hack in ``JobTickService.tick()``.
    """
    effective_phase = phase if phase is not None else record.phase

    # 1. Artifacts produced → advance
    if artifacts:
        next_p = _safe_next(effective_phase)
        if next_p in REVIEW_PHASES:
            review_status = (
                "pending" if _review_requires_human(record, next_p) else "none"
            )
            return TickAction(
                new_phase=next_p,
                new_review_status=review_status,
                message=f"{effective_phase} produced artifacts, advancing to {next_p} ({review_status} review)",
            )
        return TickAction(
            new_phase=next_p,
            message=f"{effective_phase} produced artifacts, advancing to {next_p}",
        )

    # 2. No artifacts — per-phase failure handling
    # 2a. video_rendering: retry once, then fail
    if effective_phase == "video_rendering":
        if record.execution.error is not None:
            return TickAction(
                new_phase="failed",
                message="video_rendering failed after retry",
            )
        return TickAction(
            message="video_rendering produced no artifacts, will retry next tick",
        )

    # 2b. subtitle_generating: stay in phase (critical — do not auto-advance)
    if effective_phase == "subtitle_generating":
        return TickAction(
            message="subtitle_generating produced no artifacts, staying in phase",
        )

    # 2c. tts_generating: stay in phase (critical — do not auto-advance, #253)
    if effective_phase == "tts_generating":
        return TickAction(
            message="tts_generating produced no artifacts, staying in phase",
        )

    # 2d. asset_retrieving: auto-advance on no artifacts (transitional phase)
    if effective_phase == "asset_retrieving":
        return TickAction(
            new_phase=_safe_next(effective_phase),
            message="asset_retrieving produced no artifacts, auto-advancing",
        )

    # 2e. final_rendering: a missing final.mp4 is a real failure, not a skip
    if effective_phase == "final_rendering":
        if record.execution.error is not None:
            return TickAction(
                new_phase="failed",
                message="final_rendering failed after retry",
            )
        return TickAction(
            message="final_rendering produced no artifacts, will retry next tick",
        )

    # 2f. Other handled phases: auto-advance (transitional or empty handler)
    if effective_phase in HANDLED_PHASES:
        return TickAction(
            new_phase=_safe_next(effective_phase),
            message=f"{effective_phase} produced no artifacts, auto-advancing (fallback)",
        )

    # 2f. Fallback — auto-advance
    return TickAction(
        new_phase=_safe_next(effective_phase),
        message=f"auto-advance from {effective_phase} (fallback)",
    )


# ---------------------------------------------------------------------------
# JobTickService — orchestrator-aware tick loop
# ---------------------------------------------------------------------------


def _attempts_so_far(execution: PhaseExecutionState) -> int:
    """Attempts already consumed by the current phase (0 unless retrying)."""
    return execution.current_attempt if execution.status == "retrying" else 0


def _compute_failure_transition(
    execution: PhaseExecutionState,
    handler_phase: str,
    error: ExecutionFailure,
) -> tuple[PhaseExecutionState, TickAction]:
    """Pure function: terminal / retry decision for a structured phase failure.

    No I/O, no side effects.  Returns the next execution state and the
    TickAction describing the transition, mirroring _compute_transition's
    contract so all transition logic stays unit-testable without mocks.

    ``max_attempts`` is interpreted as the number of retries *after* the
    first attempt, so a failure is terminal once ``current_attempt`` exceeds
    ``max_attempts``.  The retryable error is preserved on the retrying state
    so the tick loop never has to parse strings to apply the retry policy.
    """
    current_attempt = _attempts_so_far(execution) + 1
    terminal = not error.retryable or current_attempt > execution.max_attempts
    next_execution = PhaseExecutionState(
        status="failed" if terminal else "retrying",
        current_attempt=current_attempt,
        max_attempts=execution.max_attempts,
        error=error,
    )
    action = TickAction(
        new_phase="failed" if terminal else None,
        message=(
            f"{handler_phase} failed: {error.code}"
            if terminal
            else (
                f"{handler_phase} retrying after attempt "
                f"{current_attempt}/{execution.max_attempts + 1}"
            )
        ),
    )
    return next_execution, action


def _compute_success_execution(
    execution: PhaseExecutionState,
) -> PhaseExecutionState:
    """Pure function: execution state after a structured phase succeeded."""
    return PhaseExecutionState(
        status="succeeded",
        current_attempt=_attempts_so_far(execution) + 1,
        max_attempts=execution.max_attempts,
    )


class JobTickService:
    """Deep module: job lifecycle tick behind a two-method interface.

    Coordinates the load → _compute_transition → run handler →
    _transition_after_artifacts → persist → log lifecycle for a single job.
    """

    def __init__(
        self,
        orchestrator: PhaseOrchestrator,
        repo: FileStoreRepository,
        *,
        config_reader: "ConfigReader | None" = None,
        sleep_fn: "Callable[[float], None] | None" = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._repo = repo
        self._config = config_reader
        self._sleep_fn: "Callable[[float], None]" = (
            sleep_fn if sleep_fn is not None else (lambda _s: None)
        )

    def tick(
        self,
        project_id: str,
        job_id: str,
        product: str,
        *,
        root_dir: Path,
        project_dir: Path,
        options: dict[str, str] | None = None,
    ) -> TickSummary:
        """Chain-advance a job through consecutive phases in one pass.

        Each step reloads the JobRecord from disk so that external edits
        (cancel, voice switch, etc.) made during execution are respected.
        The chain stops at the first unapproved review gate or terminal
        phase, whichever comes first.

        Transient phase failures are retried inline with exponential
        backoff (2/4/8 s) until ``max_attempts`` retries (default 3) are
        exhausted, for a maximum of ``max_attempts + 1`` total attempts.
        Non-retryable failures go terminal immediately without backoff.

        Parameters
        ----------
        project_id : str
            Project the job belongs to.
        job_id : str
            Unique job identifier.
        product : str
            Product name for the pipeline.
        root_dir : Path
            Root directory (parent of ``workspace/``).
        project_dir : Path
            Project working directory.
        options : dict or None
            Extra options forwarded to the phase context (e.g.
            ``manual_script``, ``uploaded_audio_path``, ``language``).

        Returns
        -------
        TickSummary
            Describes the final state reached during this tick pass.

        Raises
        ------
        PhaseExecutionError
            When a phase handler raises an unexpected exception.
        """
        record = self._repo.load_job(project_id, job_id)

        initial_phase = record.phase
        first = True
        last_summary: TickSummary | None = None

        while True:
            # Reload each iteration except the first to observe external
            # edits made between steps (cancel, voice switch, etc.).
            if not first:
                record = self._repo.load_job(project_id, job_id)
            first = False

            # Terminal check after reload — an external edit may have
            # moved the job to a terminal state between steps.
            if record.phase in _TERMINAL_PHASES:
                if last_summary is None:
                    return _build_tick_summary(initial_phase, TickAction())
                return last_summary

            record, summary = self._tick_step(
                record,
                project_id,
                job_id,
                product,
                root_dir=root_dir,
                project_dir=project_dir,
                options=options,
            )
            last_summary = summary

            # Stop chaining at natural boundaries:
            #  - Nothing happened (skipped / waiting for human)
            #  - Terminal phase reached
            #  - Review gate that needs human approval
            if summary.action == "skipped":
                return summary
            if record.phase in _TERMINAL_PHASES:
                return summary
            if (
                record.phase in REVIEW_PHASES
                and _review_requires_human(record, record.phase)
                and record.review_status not in ("approved",)
            ):
                return summary

        return last_summary or _build_tick_summary(initial_phase, TickAction())

    def _build_phase_context(
        self,
        record: JobRecord,
        project_id: str,
        job_id: str,
        product: str,
        *,
        root_dir: Path,
        project_dir: Path,
        options: dict[str, str] | None = None,
    ) -> PhaseContext:
        """Build a fresh PhaseContext from the current JobRecord.

        Rebuilt before every handler attempt (including retries) so external
        edits to the record (cancel, voice switch, etc.) are observed.
        """
        scene_folder_paths: list[str] = []
        transition_duration_ms = 500
        scene_config: dict[str, Any] = {}
        if record.mode == "import":
            if self._config is not None:
                scene_cfg = self._config.get_scene_config(product_id=product)
            else:
                from packages.provider_config.config_reader import ConfigReader

                scene_cfg = ConfigReader().get_scene_config(product_id=product)
            scene_config = scene_cfg
            scene_folder_paths = list(record.scene_folder_ids) or [
                entry.get("path", "")
                for entry in scene_cfg.get("folders", [])
                if entry.get("path")
            ]
            transition_duration_ms = scene_cfg.get("transition_duration_ms", 500)

            if record.manual_script:
                job_dir = project_dir / "runtime" / "jobs" / job_id
                job_dir.mkdir(parents=True, exist_ok=True)
                script_path = job_dir / f"{record.product}口播文案.txt"
                script_path.write_text(record.manual_script, encoding="utf-8")

        merged_options: dict[str, Any] = dict(options or {})
        if record.manual_script:
            merged_options["manual_script"] = record.manual_script
        if record.tts_model:
            merged_options["tts_model"] = record.tts_model
        if record.tts_voice:
            merged_options["tts_voice"] = record.tts_voice
        # Forward audio_source so the TTS handler can skip synthesis for
        # upload / library audio jobs (#249).
        merged_options["audio_source"] = record.audio_source

        return PhaseContext(
            job_id=job_id,
            project_dir=project_dir,
            root_dir=root_dir,
            product=product,
            brand=record.brand,
            options=merged_options,
            scene_folder_paths=scene_folder_paths,
            transition_duration_ms=transition_duration_ms,
            scene_config=scene_config,
        )

    def _tick_step(
        self,
        record: JobRecord,
        project_id: str,
        job_id: str,
        product: str,
        *,
        root_dir: Path,
        project_dir: Path,
        options: dict[str, str] | None = None,
    ) -> tuple[JobRecord, TickSummary]:
        """Single phase advancement with inline retry for transient failures.

        On retryable failure the handler is re-executed after exponential
        backoff (2/4/8 s).  ``max_attempts`` is the number of retries after
        the first attempt; when the total attempt count reaches
        ``max_attempts + 1`` the failure becomes terminal.  The record is
        reloaded from disk before each retry so external edits (cancel, voice
        switch, etc.) made during the backoff are respected.
        """
        initial_phase = record.phase

        # 1. First transition decision (pre-handler)
        action = _compute_transition(record, ())

        # 2. Handler execution with inline retry for transient failures
        artifacts: list[ArtifactPointer] = []
        handler_ran = action.run_handler
        handler_phase: str | None = None
        primary_result: Any = None

        if action.run_handler:
            handler_phase = action.handler_phase or record.phase

            while True:
                # Mark execution as running before every handler attempt
                # (first try and retries).  The UI uses this to show "进行中".
                running_execution = record.execution.model_copy(
                    update={
                        "status": "running",
                        "current_attempt": _attempts_so_far(record.execution) + 1,
                    }
                )
                record_update: dict[str, Any] = {"execution": running_execution}
                if (
                    handler_phase == "asset_retrieving"
                    and record.asset_collection_status != "collecting"
                ):
                    record_update["asset_collection_status"] = "collecting"
                record = record.model_copy(update=record_update)
                self._repo.save_job(project_id, record)

                ctx = self._build_phase_context(
                    record,
                    project_id,
                    job_id,
                    product,
                    root_dir=root_dir,
                    project_dir=project_dir,
                    options=options,
                )
                try:
                    if action.parallel_phases:
                        all_phases = [handler_phase] + action.parallel_phases
                        phase_results = self._orchestrator.execute_phases_parallel(
                            all_phases, ctx
                        )
                        artifacts = []
                        for phase_result in phase_results.values():
                            if isinstance(phase_result, PhaseExecutionSuccess):
                                artifacts.extend(phase_result.artifacts)
                        primary_result = phase_results[handler_phase]
                        if not isinstance(primary_result, PhaseExecutionFailure):
                            for parallel_phase in action.parallel_phases:
                                parallel_result = phase_results[parallel_phase]
                                if isinstance(parallel_result, PhaseExecutionFailure):
                                    primary_result = parallel_result
                                    handler_phase = parallel_phase
                                    break
                    elif handler_phase in STRUCTURED_MEDIA_PHASES:
                        primary_result = self._orchestrator.execute_phase(
                            handler_phase, ctx
                        )
                        if (
                            isinstance(primary_result, PhaseExecutionSuccess)
                            and not primary_result.artifacts
                        ):
                            primary_result = PhaseExecutionFailure(
                                error=ExecutionFailure(
                                    code="INTERNAL_EMPTY_RESULT",
                                    message=(
                                        f"{handler_phase} reported success"
                                        " without an artifact."
                                    ),
                                    retryable=False,
                                )
                            )
                        if isinstance(primary_result, PhaseExecutionSuccess):
                            artifacts = primary_result.artifacts
                    else:
                        primary_result = None
                        artifacts = self._orchestrator.run_phase(handler_phase, ctx)
                except Exception as e:
                    raise PhaseExecutionError(job_id, handler_phase, str(e), e) from e

                # Merge new artifacts before any persistence decision so that
                # successful parallel outputs (e.g. tts_audio) survive a
                # failure of the primary phase in the same tick.
                record.artifacts = _merge_artifacts(record.artifacts, artifacts)

                if not isinstance(primary_result, PhaseExecutionFailure):
                    break  # success — exit retry loop

                # --- failure path ---
                execution, fail_action = _compute_failure_transition(
                    record.execution, handler_phase, primary_result.error
                )
                record = record.model_copy(
                    update={
                        "execution": execution,
                        "failed_phase": (
                            handler_phase if execution.status == "failed" else None
                        ),
                    }
                )

                if execution.status == "failed":
                    # Terminal failure — update phase and save.
                    record = record.model_copy(
                        update={"phase": fail_action.new_phase or "failed"}
                    )
                    self._repo.save_job(project_id, record)
                    return record, _build_tick_summary(initial_phase, fail_action)

                # Retryable — save retrying state, backoff, then reload and retry.
                self._repo.save_job(project_id, record)
                self._sleep_fn(_retry_delay(execution.current_attempt))
                reloaded = self._repo.load_job(project_id, job_id)
                if reloaded.phase in _TERMINAL_PHASES or reloaded.phase != record.phase:
                    return reloaded, _build_tick_summary(
                        initial_phase,
                        TickAction(
                            message=(
                                f"{handler_phase} retry cancelled by external edit"
                            )
                        ),
                    )
                record = reloaded
                artifacts = []
                primary_result = None

            # 4. Second transition decision after handler succeeded
            if action.new_phase is None:
                action = _transition_after_artifacts(
                    record, tuple(artifacts), phase=handler_phase
                )
            if isinstance(primary_result, PhaseExecutionSuccess):
                record = record.model_copy(
                    update={
                        "execution": _compute_success_execution(record.execution),
                        "failed_phase": None,
                    }
                )

            # After asset_retrieving handler succeeds, attempt to resolve the
            # collection status from the file it wrote.  Only upgrade (never
            # downgrade) so that mock-based tests and async-worker scenarios
            # can pre-set the field without it being clobbered (#326).
            if handler_phase == "asset_retrieving" and handler_ran:
                clips_path = (
                    project_dir / "runtime" / "jobs" / job_id / "selected_clips.json"
                )
                if clips_path.exists():
                    try:
                        clips_data = json.loads(clips_path.read_text(encoding="utf-8"))
                        has_clips = any(
                            c.get("visual_type") == "clip" for c in clips_data
                        )
                        new_status: str = "complete" if has_clips else "complete_empty"
                        if new_status != record.asset_collection_status:
                            record = record.model_copy(
                                update={"asset_collection_status": new_status}
                            )
                    except (json.JSONDecodeError, OSError):
                        pass  # keep current status — file is corrupt, retry later

        # 4b. Auto-approve asset_review: integrity checks + snapshot (#254, #326).
        # The asset_collection_status field gates whether auto-approval may
        # proceed.  When the status is still "not_started" we check the on-disk
        # file as a fallback so that jobs created before this field existed
        # (or with async workers) still work correctly.
        if (
            action.new_phase is not None
            and action.new_review_status == "approved"
            and record.phase == "asset_review"
            and (record.auto_approve or record.review_strategy == "fast_output")
        ):
            job_dir = project_dir / "runtime" / "jobs" / job_id

            # --- Gate 1: collection not started or in progress → block (#326) ---
            if record.asset_collection_status in ("not_started", "collecting"):
                # Lazy fallback: the handler may have written the file after the
                # record was persisted.  Check on-disk and upgrade the status
                # if the file is present.
                clips_path = job_dir / "selected_clips.json"
                if clips_path.exists():
                    try:
                        clips_data = json.loads(clips_path.read_text(encoding="utf-8"))
                        has_clips = any(
                            c.get("visual_type") == "clip" for c in clips_data
                        )
                        resolved: str = "complete" if has_clips else "complete_empty"
                        record = record.model_copy(
                            update={"asset_collection_status": resolved}
                        )
                        if resolved == "complete":
                            # Fall through to Gate 3 (validate + snapshot)
                            pass
                        else:
                            # complete_empty → block at Gate 2 below
                            pass
                    except (json.JSONDecodeError, OSError):
                        pass  # file is unreadable — block below

                if record.asset_collection_status in ("not_started", "collecting"):
                    import logging

                    _log = logging.getLogger(__name__)
                    _log.warning(
                        f"[Tick] auto-approve blocked for {job_id}: "
                        f"asset collection {record.asset_collection_status},"
                        f" staying in asset_review"
                    )
                    action.new_phase = None
                    action.new_review_status = None
                    action.message = (
                        f"auto-approve blocked: asset collection"
                        f" {record.asset_collection_status}"
                    )
                    record = record.model_copy(update={"review_status": "pending"})
                    self._repo.save_job(project_id, record)
                    return record, _build_tick_summary(initial_phase, action)

            # --- Gate 2: collection complete but empty → require human (#326) ---
            if record.asset_collection_status == "complete_empty":
                import logging

                _log = logging.getLogger(__name__)
                _log.warning(
                    f"[Tick] auto-approve blocked for {job_id}: "
                    f"no clips collected, requiring human review"
                )
                action.new_phase = None
                action.new_review_status = None
                action.message = (
                    "auto-approve blocked: no clips collected, requires human review"
                )
                record = record.model_copy(update={"review_status": "pending"})
                self._repo.save_job(project_id, record)
                return record, _build_tick_summary(initial_phase, action)

            # --- Gate 3: collection complete → validate & snapshot ---
            try:
                clips = validate_assets(job_dir, force=True)
                write_reviewed_snapshot(job_dir, clips)
            except AssetValidationError:
                import logging

                _log = logging.getLogger(__name__)
                _log.warning(
                    f"[Tick] auto-approve blocked for {job_id}: "
                    f"unresolved clips present, staying in asset_review"
                )
                action.new_phase = None
                action.new_review_status = None
                action.message = (
                    "auto-approve blocked: unresolved clips in asset_review"
                )
                record = record.model_copy(update={"review_status": "pending"})
                self._repo.save_job(project_id, record)
                return record, _build_tick_summary(initial_phase, action)
            except FileNotFoundError:
                # The file may legitimately be absent when the status was
                # pre-set (e.g. mock tests, async workers).  Trust the
                # explicit "complete" status and skip validation.
                if record.asset_collection_status != "complete":
                    import logging

                    _log = logging.getLogger(__name__)
                    _log.warning(
                        f"[Tick] auto-approve blocked for {job_id}: "
                        f"selected_clips.json unexpectedly missing"
                    )
                    action.new_phase = None
                    action.new_review_status = None
                    action.message = (
                        "auto-approve blocked: selected_clips.json unexpectedly missing"
                    )
                    record = record.model_copy(update={"review_status": "pending"})
                    self._repo.save_job(project_id, record)
                    return record, _build_tick_summary(initial_phase, action)

        # A lifecycle request can arrive while a handler is running.  Preserve
        # its completed artifacts, but consume the request before applying the
        # handler's next-phase transition.
        if handler_ran and action.new_phase not in {"paused", "cancelled"}:
            latest = self._repo.load_job(project_id, job_id)
            if latest.cancellation_requested or latest.pause_requested:
                record = record.model_copy(
                    update={
                        "pause_requested": latest.pause_requested,
                        "cancellation_requested": latest.cancellation_requested,
                        "paused_at": latest.paused_at,
                    }
                )
                action = _compute_transition(record, ())

        # 5. Apply phase / review_status changes
        update: dict[str, Any] = {}
        if action.new_phase is not None:
            update["phase"] = action.new_phase
            if action.new_phase == "paused":
                update["paused_from_phase"] = record.phase
                update["pause_requested"] = False
            elif action.new_phase == "cancelled":
                update["cancellation_requested"] = False
                update["pause_requested"] = False
        if action.new_review_status is not None:
            update["review_status"] = action.new_review_status

        if update:
            record = record.model_copy(update=update)

        # 6. Persist (only when something actually changed)
        if update or handler_ran:
            self._repo.save_job(project_id, record)
            if action.review_event:
                event = {
                    "job_id": job_id,
                    "project_id": project_id,
                    **action.review_event,
                }
                self._repo.append_review_event(project_id, event)

        # 7. Build summary
        return record, _build_tick_summary(initial_phase, action)

    def advance_after_report(
        self,
        project_id: str,
        job_id: str,
        manifest_files: list[dict[str, Any]],
        *,
        handler_phase: str | None = None,
        error: ExecutionFailure | None = None,
    ) -> TickSummary:
        """Worker-report entry point: advance job based on worker's output.

        Does NOT run any handler — the worker already did.
        Re-decides the transition, updates execution state, persists,
        and returns a summary.

        Parameters
        ----------
        project_id : str
            Project the job belongs to.
        job_id : str
            Unique job identifier.
        manifest_files : list[dict]
            Artifact manifest from the worker, typically
            ``payload.artifact_manifest["files"]``.
        handler_phase : str or None
            The phase the worker was dispatched to execute.  When provided
            it is used as the effective phase for transition logic,
            guarding against the dispatch-never-persists-phase edge case
            (#171).
        error : ExecutionFailure or None
            When the worker reported a failure, the structured error to
            feed into ``_compute_failure_transition`` so attempt counting
            and retry-exhaustion logic is shared with the auto-tick path.

        Returns
        -------
        TickSummary
            Describes what happened during advancement.
        """
        record = self._repo.load_job(project_id, job_id)
        initial_phase = record.phase
        effective_phase = handler_phase if handler_phase is not None else record.phase

        # ------------------------------------------------------------------
        # Worker failure path — shared retry / terminal logic
        # ------------------------------------------------------------------
        if error is not None:
            execution, action = _compute_failure_transition(
                record.execution, effective_phase, error
            )
            update: dict[str, Any] = {
                "execution": execution,
                "artifacts": record.artifacts,  # preserve existing artifacts
                "failed_phase": (
                    effective_phase if execution.status == "failed" else None
                ),
            }
            if action.new_phase is not None:
                update["phase"] = action.new_phase
            if action.new_review_status is not None:
                update["review_status"] = action.new_review_status
            record = record.model_copy(update=update)
            self._repo.save_job(project_id, record)
            return _build_tick_summary(initial_phase, action)

        # ------------------------------------------------------------------
        # Worker success path — merge artifacts, advance phase, update
        # execution state
        # ------------------------------------------------------------------
        # Build artifacts list from manifest
        new_artifacts: list[ArtifactPointer] = []
        for f in manifest_files:
            kind = _artifact_kind(f.get("relative_path", ""))
            new_artifacts.append(
                ArtifactPointer(
                    kind=kind,
                    relative_path=f.get("relative_path", ""),
                    size_bytes=f.get("size_bytes", 0),
                )
            )

        # Merge into record
        record.artifacts = _merge_artifacts(record.artifacts, new_artifacts)

        # Worker has already executed the phase — use the post-handler
        # transition with the explicit handler phase so per-phase rules
        # are applied correctly even when dispatch never persisted a
        # phase change (#171).
        action = _transition_after_artifacts(
            record, tuple(new_artifacts), phase=effective_phase
        )

        # Update execution state to record the worker's success
        execution = _compute_success_execution(record.execution)

        # Apply phase / review_status / execution changes
        update: dict[str, Any] = {"execution": execution, "failed_phase": None}
        if action.new_phase is not None:
            update["phase"] = action.new_phase
        if action.new_review_status is not None:
            update["review_status"] = action.new_review_status

        record = record.model_copy(update=update)
        self._repo.save_job(project_id, record)

        if action.review_event:
            event = {"job_id": job_id, "project_id": project_id, **action.review_event}
            self._repo.append_review_event(project_id, event)

        return _build_tick_summary(initial_phase, action)


def _artifact_kind(path: str) -> str:
    """Map artifact file path to a known kind."""
    if path.endswith("montage_segment.mp4"):
        return "montage_segment"
    if path.endswith("montage_segments.json"):
        return "montage_segments"
    if path.endswith(".txt") or path.endswith(".json"):
        return "script"
    if path.endswith(".mp3"):
        return "tts_audio"
    if path.endswith(".srt"):
        return "subtitle"
    if path.endswith(".mp4"):
        if "final" in path:
            return "final_video"
        return "source_video"
    return "unknown"
