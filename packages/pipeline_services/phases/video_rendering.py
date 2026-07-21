"""Video rendering phase handler."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from packages.pipeline_services.final_timeline import (
    align_audio,
    build_final_timeline,
    compute_scene_offset_ms,
    shift_srt,
)

from .shared import _job_dir, _to_artifact

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """video_rendering: compose the base video from the Montage Segment.

    In import mode, the optional ``scene_segment.mp4`` is concatenated before
    the ``montage_segment.mp4``.  In generate mode (no scene), the montage
    segment is used directly as ``base.mp4``.

    The authoritative ``montage_segments.json`` produced by
    ``montage_assembling`` drives the Final Timeline so the montage layout is
    immutable and review-time decisions are preserved exactly.
    """
    job_dir = _job_dir(ctx)
    workspace_dir = ctx.root_dir / "workspace"
    base_path = job_dir / "base.mp4"
    montage_path = job_dir / "montage_segment.mp4"
    scene_path = job_dir / "scene_segment.mp4"

    if not montage_path.exists():
        print(f"[VIDEO] No montage segment for {ctx.job_id}", flush=True)
        return []

    scene_exists = scene_path.exists()

    if scene_exists:
        # Concat scene segment + montage segment, normalizing both inputs.
        ffmpeg = orchestrator._get_ffmpeg_path()
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(scene_path),
                "-i",
                str(montage_path),
                "-filter_complex",
                "[0:v]settb=AVTB,fps=30,scale=720:1280:force_original_aspect_ratio=decrease,"
                "pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,format=pix_fmts=yuv420p[v0];"
                "[1:v]settb=AVTB,fps=30,scale=720:1280:force_original_aspect_ratio=decrease,"
                "pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1,format=pix_fmts=yuv420p[v1];"
                "[v0][v1]concat=n=2:v=1:a=0[v]",
                "-map",
                "[v]",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(base_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        print(f"[VIDEO] Concatenated scene + montage for {ctx.job_id}", flush=True)
    else:
        shutil.copy2(montage_path, base_path)
        print(f"[VIDEO] Using montage segment as base for {ctx.job_id}", flush=True)

    if base_path.exists():
        trim_params: list[dict] = []
        segments_path = job_dir / "montage_segments.json"
        if segments_path.exists():
            try:
                trim_params = json.loads(segments_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        _inject_av_alignment(orchestrator, ctx, job_dir, base_path, trim_params)
        return [_to_artifact("video_base", base_path, workspace_dir)]

    print(f"[VIDEO WARN] base.mp4 not produced for {ctx.job_id}", flush=True)
    return []


def _inject_av_alignment(
    orchestrator: PhaseOrchestrator,
    ctx: PhaseContext,
    job_dir: Path,
    base_path: Path,
    trim_params: list[dict],
) -> None:
    """Shift TTS audio + subtitles to the montage start and persist the
    authoritative Final Timeline (issue #179).

    The scene segment occupies ``[0, scene_ms)`` with no voice/subtitle;
    the montage (voice + subtitle) is offset by ``scene_ms``.  Produces
    ``audio_aligned.mp3``, ``subtitles_offset.srt`` and ``final_timeline.json``
    next to ``base.mp4``.  On alignment failure the original audio is kept
    and the timeline is marked ``aligned: false`` (best-effort render).
    """
    audio_path = job_dir / "audio.mp3"
    srt_path = job_dir / "subtitles.srt"
    scene_path = job_dir / "scene_segment.mp4"
    if not audio_path.exists() or not trim_params:
        return

    scene_ms = compute_scene_offset_ms(scene_path)
    base_ms = int(round(orchestrator._get_media_duration(base_path) * 1000))

    aligned = True
    # 1. Offset TTS audio to the montage start, sized to the base length.
    try:
        align_audio(
            audio_path,
            job_dir / "audio_aligned.mp3",
            offset_ms=scene_ms,
            total_ms=base_ms,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort alignment
        aligned = False
        print(f"[VIDEO WARN] audio align failed, using original: {exc}", flush=True)

    # 2. Offset subtitles by the same scene duration (if present).
    if srt_path.exists():
        shifted = shift_srt(srt_path.read_text(encoding="utf-8"), scene_ms)
        (job_dir / "subtitles_offset.srt").write_text(shifted, encoding="utf-8")

    # 3. Persist the authoritative Final Timeline (render-time, no dir scan).
    timeline = build_final_timeline(
        scene_ms=scene_ms,
        montage_segments=trim_params,
        aligned=aligned,
    )
    (job_dir / "final_timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Rerender changed the Final Timeline — any prior export is now stale (#180).
    try:
        from packages.pipeline_services.export_task import ExportTaskService

        ExportTaskService(
            job_id=ctx.job_id,
            job_dir=job_dir,
            workspace_dir=ctx.project_dir.parent,
            project_dir=ctx.project_dir,
            export_dir=ctx.project_dir / "runtime" / "exports",
        ).mark_stale()
    except Exception:  # noqa: BLE001 — never block rendering on export cleanup
        pass
    print(
        f"[VIDEO] Final Timeline: scene_ms={scene_ms} aligned={aligned} "
        f"segments={len(timeline['segments'])} fp={timeline['fingerprint'][:8]}",
        flush=True,
    )
