"""Precise MP4 segmentation + timeline.json 2.0 (issue #181).

Splits ``final.mp4`` into one ``seg_NNN.mp4`` per Final Timeline segment using
exact-boundary re-encoding, and converts the render-time Final Timeline into a
flat playback-order ``timeline.json`` 2.0 that references each rendered chunk.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable

from packages.pipeline_services.media_utils import get_ffmpeg_path

__all__ = ["build_timeline_2", "segment_final_video"]


def build_timeline_2(final_timeline: dict[str, Any]) -> dict[str, Any]:
    """Convert a render-time Final Timeline into flat playback-order schema 2.0.

    Each segment gains a ``rendered_file`` (``final/seg_NNN.mp4``); montage
    segments also carry ``source_file`` — the basename of the original asset
    recorded in the segment's ``source.file_path``.  Blank/scene segments have
    no montage source asset, so the field is omitted.
    """
    segments: list[dict[str, Any]] = []
    for index, seg in enumerate(final_timeline.get("segments", []), start=1):
        out: dict[str, Any] = {
            "kind": seg.get("kind"),
            "start_ms": seg.get("start_ms"),
            "end_ms": seg.get("end_ms"),
            "sentence_index": seg.get("sentence_index"),
            "text": seg.get("text", ""),
            "rendered_file": f"final/seg_{index:03d}.mp4",
        }
        source_path = (seg.get("source") or {}).get("file_path", "")
        if seg.get("kind") == "montage" and source_path:
            out["source_file"] = Path(source_path).name
        segments.append(out)

    return {
        "version": "2.0",
        "duration_ms": final_timeline.get("duration_ms"),
        "fingerprint": final_timeline.get("fingerprint"),
        "segments": segments,
    }


def segment_final_video(
    final_mp4: Path,
    segments: list[dict[str, Any]],
    out_dir: Path,
    *,
    progress_callback: Callable[[int], None] | None = None,
) -> list[Path]:
    """Split *final_mp4* into one ``seg_NNN.mp4`` per timeline segment.

    Re-encodes (never stream-copies) so each chunk starts exactly on its
    segment boundary regardless of keyframe placement.  Returns the produced
    segment paths in playback order.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = get_ffmpeg_path()
    produced: list[Path] = []

    for index, seg in enumerate(segments, start=1):
        start_s = seg["start_ms"] / 1000.0
        duration_s = (seg["end_ms"] - seg["start_ms"]) / 1000.0
        out_path = out_dir / f"seg_{index:03d}.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-ss",
                f"{start_s:.3f}",
                "-i",
                str(final_mp4),
                "-t",
                f"{duration_s:.3f}",
                "-map",
                "0",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-movflags",
                "+faststart",
                str(out_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
        produced.append(out_path)
        if progress_callback is not None:
            progress_callback(round(index / len(segments) * 100))

    return produced
