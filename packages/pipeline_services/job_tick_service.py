"""Pure-function state machine for job phase transitions.

Defines types (TickAction, TickSummary, PhaseExecutionError) and the pure
transition function _compute_transition that decides what should happen next
given a JobRecord and the artifacts produced by the current phase handler.

This module has zero I/O and zero side effects — all transition logic is
contained in a single referentially transparent function.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from packages.domain_core.models import ArtifactPointer, JobRecord
from packages.domain_core.state import PHASE_ORDER, next_phase
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
)

if TYPE_CHECKING:
    from packages.provider_config.config_reader import ConfigReader

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REVIEW_PHASES: frozenset[str] = frozenset(
    {"script_review", "tts_review", "asset_review", "final_review"}
)

HANDLED_PHASES: frozenset[str] = frozenset(
    {
        "script_generating",
        "tts_generating",
        "tts_review",
        "subtitle_generating",
        "asset_retrieving",
        "video_rendering",
        "final_rendering",
    }
)

_TERMINAL_PHASES: frozenset[str] = frozenset(
    {"completed", "failed", "cancelled", "paused"}
)


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
    """Merge *new_artifacts* into *existing*, deduplicating by kind."""
    existing_kinds = {a.kind for a in existing}
    result = list(existing)
    for a in new_artifacts:
        if a.kind not in existing_kinds:
            result.append(a)
            existing_kinds.add(a.kind)
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
        return TickAction(
            run_handler=True,
            handler_phase="scene_assembling",
            parallel_phases=["tts_generating"],
            new_phase="subtitle_generating",
            message="scene_assembling + tts_generating (parallel) → subtitle_generating",
        )

    if phase == "subtitle_generating" and record.mode == "import":
        if record.skip_subtitle:
            return TickAction(
                new_phase="montage_assembling",
                message="skip subtitle_generating (import mode) → montage_assembling",
            )
        if artifacts:
            return TickAction(
                new_phase="montage_assembling",
                message="subtitle_generating → montage_assembling (import mode)",
            )
        # fall through: no artifacts, not skipping → run subtitle handler

    if phase == "montage_assembling":
        return TickAction(
            run_handler=True,
            handler_phase="montage_assembling",
            new_phase="video_rendering",
            message="montage_assembling → video_rendering",
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
        if record.auto_approve and record.review_status not in ("approved", "pending"):
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
    # 4. Queued → route to script_generating handler
    # ------------------------------------------------------------------
    if phase == "queued":
        if record.mode == "import":
            return TickAction(
                new_phase="scene_assembling",
                message="queued → scene_assembling (import mode, no handler yet)",
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

    # Import mode: subtitle_generating → montage_assembling (not asset_retrieving)
    if record.mode == "import" and effective_phase == "subtitle_generating" and artifacts:
        return TickAction(
            new_phase="montage_assembling",
            message="subtitle_generating → montage_assembling (import mode)",
        )

    # 1. Artifacts produced → advance
    if artifacts:
        next_p = _safe_next(effective_phase)
        if next_p in REVIEW_PHASES:
            review_status = "none" if record.auto_approve else "pending"
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
        if "video_rendering" in (record.last_error or ""):
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

    # 2c. asset_retrieving: auto-advance on no artifacts (transitional phase)
    if effective_phase == "asset_retrieving":
        return TickAction(
            new_phase=_safe_next(effective_phase),
            message="asset_retrieving produced no artifacts, auto-advancing",
        )

    # 2d. Other handled phases: auto-advance (transitional or empty handler)
    if effective_phase in HANDLED_PHASES:
        return TickAction(
            new_phase=_safe_next(effective_phase),
            message=f"{effective_phase} produced no artifacts, auto-advancing (fallback)",
        )

    # 2e. Fallback — auto-advance
    return TickAction(
        new_phase=_safe_next(effective_phase),
        message=f"auto-advance from {effective_phase} (fallback)",
    )


# ---------------------------------------------------------------------------
# JobTickService — orchestrator-aware tick loop
# ---------------------------------------------------------------------------


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
    ) -> None:
        self._orchestrator = orchestrator
        self._repo = repo
        self._config = config_reader

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
        """Auto-tick entry point: advances a single job by one step.

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
            Describes what happened during this tick cycle.

        Raises
        ------
        PhaseExecutionError
            When a phase handler raises an unexpected exception.
        """
        # 1. Load current state
        record = self._repo.load_job(project_id, job_id)
        initial_phase = record.phase

        # 2. First transition decision (pre-handler)
        action = _compute_transition(record, ())

        # 3. Execute handler(s) if the transition requires it
        artifacts: list[ArtifactPointer] = []
        if action.run_handler:
            # Populate scene config for import mode
            scene_folder_paths: list[str] = []
            transition_duration_ms: int = 500
            scene_config: dict[str, Any] = {}
            if record.mode == "import":
                # Resolve scene config: ConfigReader > AppConfigManager fallback
                if self._config is not None:
                    scene_cfg = self._config.get_scene_config(product_id=product)
                else:
                    from packages.provider_config.app_config import AppConfigManager
                    app_cfg = AppConfigManager()
                    product_cfg = app_cfg.get_product_config()
                    scene_cfg = product_cfg.get("scene", {})
                scene_config = scene_cfg
                scene_folder_paths = [
                    entry.get("path", "")
                    for entry in scene_cfg.get("folders", [])
                    if entry.get("path")
                ]
                transition_duration_ms = scene_cfg.get("transition_duration_ms", 500)

                # Write manual_script so TTS handler can discover it in import mode
                if record.manual_script:
                    job_dir = project_dir / "runtime" / "jobs" / job_id
                    job_dir.mkdir(parents=True, exist_ok=True)
                    script_path = job_dir / f"{record.product}口播文案.txt"
                    script_path.write_text(record.manual_script, encoding="utf-8")

            ctx = PhaseContext(
                job_id=job_id,
                project_dir=project_dir,
                root_dir=root_dir,
                product=product,
                brand=record.brand,
                options=options or {},
                scene_folder_paths=scene_folder_paths,
                transition_duration_ms=transition_duration_ms,
                scene_config=scene_config,
            )
            handler_phase = action.handler_phase or record.phase

            try:
                if action.parallel_phases:
                    # Parallel dispatch for import mode
                    all_phases = [handler_phase] + action.parallel_phases
                    phase_results = self._orchestrator.run_phases_parallel(
                        all_phases, ctx
                    )
                    for ph_artifacts in phase_results.values():
                        artifacts.extend(ph_artifacts)
                else:
                    artifacts = self._orchestrator.run_phase(handler_phase, ctx)
            except Exception as e:
                raise PhaseExecutionError(job_id, handler_phase, str(e), e) from e

            # Merge new artifacts
            record.artifacts = _merge_artifacts(record.artifacts, artifacts)

            # 4. Second transition decision after handler ran
            if action.new_phase is not None:
                # Auto-approve or similar: first action already includes the
                # target transition — use it directly.
                pass
            else:
                # Pass explicit phase so per-phase rules use the handler's phase
                # instead of the record's current phase.
                action = _transition_after_artifacts(
                    record, tuple(artifacts), phase=handler_phase
                )

        # 5. Apply phase / review_status changes
        update: dict[str, Any] = {}
        if action.new_phase is not None:
            update["phase"] = action.new_phase
        if action.new_review_status is not None:
            update["review_status"] = action.new_review_status

        if update:
            record = record.model_copy(update=update)

        # 6. Persist (only when something actually changed)
        if update or action.run_handler:
            self._repo.save_job(project_id, record)
            if action.review_event:
                event = {
                    "job_id": job_id,
                    "project_id": project_id,
                    **action.review_event,
                }
                self._repo.append_review_event(project_id, event)

        # 7. Build summary
        return _build_tick_summary(initial_phase, action)

    def advance_after_report(
        self,
        project_id: str,
        job_id: str,
        manifest_files: list[dict[str, Any]],
    ) -> TickSummary:
        """Worker-report entry point: advance job based on worker's output.

        Does NOT run any handler — the worker already did.
        Only re-decides the transition, persists, and returns a summary.

        Parameters
        ----------
        project_id : str
            Project the job belongs to.
        job_id : str
            Unique job identifier.
        manifest_files : list[dict]
            Artifact manifest from the worker, typically
            ``payload.artifact_manifest["files"]``.

        Returns
        -------
        TickSummary
            Describes what happened during advancement.
        """
        record = self._repo.load_job(project_id, job_id)
        initial_phase = record.phase

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

        # Worker has already executed the phase — use the unified
        # compute_transition entry point (non-empty artifacts → post-handler path)
        action = _compute_transition(record, tuple(new_artifacts))

        # Apply phase / review_status changes
        update: dict[str, Any] = {}
        if action.new_phase is not None:
            update["phase"] = action.new_phase
        if action.new_review_status is not None:
            update["review_status"] = action.new_review_status

        if update:
            record = record.model_copy(update=update)
            self._repo.save_job(project_id, record)

        if action.review_event:
            event = {"job_id": job_id, "project_id": project_id, **action.review_event}
            self._repo.append_review_event(project_id, event)

        return _build_tick_summary(initial_phase, action)


def _artifact_kind(path: str) -> str:
    """Map artifact file path to a known kind."""
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
