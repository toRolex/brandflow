"""Final rendering phase handler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from packages.pipeline_services.logging_utils import get_pipeline_logger
from packages.pipeline_services.media_probe import is_decodable_video, probe_media

from .shared import _job_dir, _to_artifact

_LOGGER = get_pipeline_logger(__name__)

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """final_rendering: burn subtitles, music, cover title into final video.

    Reads settings from the job JSON file (written by the UI) rather than
    ``ctx.options``, since that is where the UI persists them.
    """
    job_dir = _job_dir(ctx)
    final_path = job_dir / "final.mp4"
    base_path = job_dir / "base.mp4"
    audio_path = job_dir / "audio.mp3"
    srt_path = job_dir / "subtitles.srt"
    job_json_path = ctx.layout.job_record_path(ctx.project_dir.name, ctx.job_id)

    skip_subtitle = False
    music_path = None
    music_volume = 80
    cover_title_data = None

    if job_json_path.exists():
        job_data = json.loads(job_json_path.read_text(encoding="utf-8"))
        skip_subtitle = job_data.get("skip_subtitle", False)
        music_track = job_data.get("music_track_path", "")
        music_volume = job_data.get("music_volume", 80)
        ct = job_data.get("cover_title")
        if ct and ct.get("text"):
            cover_title_data = ct
        if music_track:
            music_path = ctx.root_dir / music_track
            if not music_path.exists():
                music_path = None

    actual_srt_path = None if skip_subtitle else srt_path
    # Prefer AV-aligned audio + offset subtitles produced by video_rendering
    # (issue #179): TTS/subtitle shifted to the montage start.
    aligned_audio = job_dir / "audio_aligned.mp3"
    offset_srt = job_dir / "subtitles_offset.srt"
    if aligned_audio.exists():
        audio_path = aligned_audio
    if not skip_subtitle and offset_srt.exists():
        actual_srt_path = offset_srt
    cond = (
        f"base={base_path.exists()} audio={audio_path.exists()}"
        f" skip_subtitle={skip_subtitle} srt={srt_path.exists()}"
    )
    logger = _LOGGER.bind(ctx.job_id)
    logger.info("[FINAL] %s", cond)
    if (
        base_path.exists()
        and audio_path.exists()
        and (skip_subtitle or srt_path.exists())
    ):
        orchestrator._video_svc.burn_final_video(
            base_path,
            audio_path,
            actual_srt_path,
            final_path,
            cover_clip_path=None,
            cover_title=cover_title_data,
            music_path=music_path,
            music_volume=music_volume,
        )

    if final_path.exists():
        media_info = probe_media(final_path)
        if (
            media_info["video_codec"] is None
            or not media_info["duration"]
            or not is_decodable_video(final_path)
        ):
            logger.error("[FINAL] final.mp4 is not playable; rejecting artifact")
            return []
        logger.info(
            "[FINAL] final.mp4 produced (%s bytes)", final_path.stat().st_size
        )
        return [_to_artifact("final_video", final_path, ctx.layout)]
    logger.warning("[FINAL] final.mp4 NOT produced")
    return []
