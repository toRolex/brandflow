"""Subtitle generation phase handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .shared import _discover_script, _discover_sentence_timings, _job_dir, _to_artifact

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """subtitle_generating: build SRT from audio + script text.

    When ``sentences.json`` is present, subtitle chunks are constrained to
    the Script Sentence boundaries so that no subtitle block crosses a
    sentence boundary.
    """
    job_dir = _job_dir(ctx)
    workspace_dir = ctx.root_dir / "workspace"
    audio_path = job_dir / "audio.mp3"
    srt_path = job_dir / "subtitles.srt"
    print(
        f"[SUBTITLE] audio exists={audio_path.exists()}, srt exists={srt_path.exists()}",
        flush=True,
    )
    if audio_path.exists():
        script_text = _discover_script(job_dir) or ""
        print(
            f"[SUBTITLE] script found={bool(script_text)}, len={len(script_text)}",
            flush=True,
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
                print(f"[SUBTITLE] srt generated={srt_path.exists()}", flush=True)
            except Exception as e:
                print(f"[SUBTITLE ERROR] {type(e).__name__}: {e}", flush=True)
                import traceback

                traceback.print_exc()
    else:
        print(f"[SUBTITLE WARN] audio.mp3 not found in {job_dir}", flush=True)
    if srt_path.exists():
        return [_to_artifact("subtitle", srt_path, workspace_dir)]
    return []
