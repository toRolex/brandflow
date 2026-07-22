"""Montage assembly phase handler."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from packages.domain_core.models import ExecutionFailure

from .shared import _discover_sentence_timings, _job_dir, _to_artifact

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """montage_assembling: build the independent Montage Segment.

    Consumes the immutable ``reviewed_assets.json`` snapshot, the TTS audio,
    and canonical sentence timings to produce ``montage_segment.mp4`` plus
    the authoritative ``montage_segments.json`` trim-parameter manifest.

    A missing snapshot/audio/timings, unresolved decisions, or missing clip
    files are raised as structured failures by the shared input loader.
    """
    workspace_dir = ctx.root_dir / "workspace"
    job_dir = _job_dir(ctx)
    selected, sentence_timings, error = load_montage_inputs(ctx)
    if error is not None:
        # Validation should have caught this, but if it didn't, raise so
        # execute_phase converts it into a structured MEDIA_INPUT_INVALID.
        raise ValueError(error.message)

    audio_path = job_dir / "audio.mp3"
    montage_path = job_dir / "montage_segment.mp4"
    segments_path = job_dir / "montage_segments.json"

    trim_params = orchestrator._video_svc.build_base_video(
        ctx.project_dir,
        {
            "job_id": ctx.job_id,
            "asset_bundle": {
                "audio_path": str(audio_path),
                "selected_clips": selected,
            },
            "sequence": 1,
        },
        montage_path,
        sentence_timings=sentence_timings if sentence_timings else None,
    )
    if trim_params is None:
        trim_params = []

    if not montage_path.exists():
        print(
            f"[MONTAGE] build_base_video did not produce {montage_path}",
            flush=True,
        )
        return []

    segments_path.write_text(
        json.dumps(trim_params, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result: list = []
    if montage_path.exists():
        result.append(_to_artifact("montage_segment", montage_path, workspace_dir))
    if segments_path.exists():
        result.append(_to_artifact("montage_segments", segments_path, workspace_dir))
    return result


def load_montage_inputs(
    ctx: PhaseContext,
) -> tuple[list[dict], list[dict], ExecutionFailure | None]:
    """Load and validate the immutable inputs for ``montage_assembling``.

    Returns (selected_clips, sentence_timing_dicts, error).  The same
    checks are used by ``validate_phase_input`` and ``run`` so the
    pre-execution contract and runtime contract cannot drift.
    """
    job_dir = _job_dir(ctx)
    audio_path = job_dir / "audio.mp3"
    snapshot_path = job_dir / "reviewed_assets.json"
    sentences_path = job_dir / "sentences.json"

    if not snapshot_path.exists():
        return (
            [],
            [],
            ExecutionFailure(
                code="MONTAGE_SNAPSHOT_MISSING",
                message=(
                    "The reviewed asset snapshot is missing; "
                    "asset review must be approved first."
                ),
                retryable=False,
            ),
        )
    if not audio_path.exists():
        return (
            [],
            [],
            ExecutionFailure(
                code="MONTAGE_AUDIO_MISSING",
                message="TTS audio is required before the montage can be assembled.",
                retryable=False,
            ),
        )
    if not sentences_path.exists():
        return (
            [],
            [],
            ExecutionFailure(
                code="MONTAGE_TIMINGS_MISSING",
                message=(
                    "Sentence timings are required before the montage can be assembled."
                ),
                retryable=False,
            ),
        )

    try:
        selected = json.loads(snapshot_path.read_text(encoding="utf-8"))
        sentence_timings = [t.model_dump() for t in _discover_sentence_timings(job_dir)]
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        return (
            [],
            [],
            ExecutionFailure(
                code="MONTAGE_INPUT_INVALID",
                message=f"Montage input is invalid: {exc}",
                retryable=False,
            ),
        )

    if not selected:
        return (
            [],
            [],
            ExecutionFailure(
                code="MONTAGE_DECISIONS_MISSING",
                message=(
                    "At least one reviewed asset decision is required to build the montage."
                ),
                retryable=False,
            ),
        )

    unresolved = [c for c in selected if c.get("visual_type") == "unresolved"]
    if unresolved:
        return (
            [],
            [],
            ExecutionFailure(
                code="MONTAGE_UNRESOLVED_DECISIONS",
                message=(
                    f"{len(unresolved)} reviewed asset decision(s) are still unresolved."
                ),
                retryable=False,
            ),
        )

    missing = [
        c
        for c in selected
        if c.get("visual_type") == "clip"
        and c.get("file_path")
        and not Path(c["file_path"]).exists()
    ]
    if missing:
        return (
            [],
            [],
            ExecutionFailure(
                code="MONTAGE_CLIP_FILE_MISSING",
                message=f"Reviewed clip file not found: {missing[0].get('file_path', '')}",
                retryable=False,
            ),
        )

    return selected, sentence_timings, None
