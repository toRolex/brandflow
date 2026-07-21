"""Shared helpers for phase handlers.

These functions are stateless and operate only on the supplied context or paths.
They are wrapped as methods on ``PhaseOrchestrator`` so handlers can access them
through the orchestrator instance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from packages.domain_core.models import ArtifactPointer
from packages.pipeline_services.sentence_tts_service import SentenceTiming

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import PhaseContext


def to_url_path(path: Path, workspace_dir: Path) -> str:
    """Convert a workspace-relative *Path* to a URL-safe forward-slash string."""
    return path.relative_to(workspace_dir).as_posix()


def _job_dir(ctx: PhaseContext) -> Path:
    """Return (and ensure) the job's runtime output directory."""
    d = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _to_artifact(kind: str, path: Path, workspace_dir: Path) -> ArtifactPointer:
    """Build an ``ArtifactPointer`` from an absolute file path."""
    rel = to_url_path(path, workspace_dir)
    return ArtifactPointer(
        kind=kind,
        relative_path=rel,
        url=f"/workspace/{rel}",
        size_bytes=path.stat().st_size if path.exists() else 0,
    )


def _discover_script(job_dir: Path) -> str | None:
    """Return the script text from *口播文案.txt or *口播文案.json, or None."""
    for p in job_dir.glob("*口播文案.txt"):
        return p.read_text(encoding="utf-8").strip() or None
    for p in job_dir.glob("*口播文案.json"):
        jdata = json.loads(p.read_text(encoding="utf-8"))
        text = jdata.get("text", "").strip()
        return text or None
    return None


def _discover_sentence_timings(job_dir: Path) -> list[SentenceTiming]:
    """Return sentence timings from sentences.json if present and valid."""
    path = job_dir / "sentences.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [SentenceTiming.model_validate(item) for item in data]
    except Exception as exc:  # noqa: BLE001
        print(
            f"[TTS TIMING WARN] Failed to load sentence timings: {exc}", flush=True
        )
        return []


def _get_ffmpeg_path() -> str:
    """Resolve ffmpeg path via media_utils."""
    from packages.pipeline_services.media_utils import get_ffmpeg_path as _gfp

    return _gfp()


def _get_media_duration(file_path: Path) -> float:
    """Get media duration in seconds via ffprobe."""
    from packages.pipeline_services.media_utils import get_media_duration as _gmd

    return _gmd(file_path)


def _fallback_category_suggestion_model() -> str:
    """Fallback: return the default category suggestion model."""
    return "deepseek-v4-flash"
