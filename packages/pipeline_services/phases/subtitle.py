"""Subtitle generation phase handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from packages.pipeline_services.logging_utils import get_pipeline_logger

from .shared import _discover_script, _discover_sentence_timings, _job_dir, _to_artifact

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )

_LOGGER = get_pipeline_logger(__name__)


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """subtitle_generating: build SRT from audio + script text.

    When ``sentences.json`` is present, subtitle chunks are constrained to
    the Script Sentence boundaries so that no subtitle block crosses a
    sentence boundary.
    """
    job_dir = _job_dir(ctx)
    logger = _LOGGER.bind(ctx.job_id)
    audio_path = job_dir / "audio.mp3"
    srt_path = job_dir / "subtitles.srt"
    logger.debug(
        "[SUBTITLE] audio exists=%s, srt exists=%s",
        audio_path.exists(),
        srt_path.exists(),
    )
    if audio_path.exists():
        script_text = _discover_script(job_dir) or ""
        logger.debug(
            "[SUBTITLE] script found=%s, len=%s", bool(script_text), len(script_text)
        )
        if script_text:
            try:
                sentence_timings = _discover_sentence_timings(job_dir)
                if sentence_timings:
                    orchestrator._subtitle_svc.build_srt(
                        audio_path,
                        srt_path,
                        script_text,
                        sentence_timings=sentence_timings,
                    )
                else:
                    orchestrator._subtitle_svc.build_srt(
                        audio_path, srt_path, script_text
                    )
                logger.info("[SUBTITLE] srt generated=%s", srt_path.exists())
            except Exception as e:
                logger.error("[SUBTITLE ERROR] %s: %s", type(e).__name__, e, exc_info=True)
    else:
        logger.warning("[SUBTITLE WARN] audio.mp3 not found in %s", job_dir)
    if srt_path.exists():
        return [_to_artifact("subtitle", srt_path, ctx.layout)]
    return []
