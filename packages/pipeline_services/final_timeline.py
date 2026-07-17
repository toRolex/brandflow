"""Authoritative Final Timeline generation (issue #179).

This module builds the Final Timeline at render time from the *actual* render
inputs — the reviewed-assets snapshot, measured per-sentence timings and the
probed scene duration — rather than by scanning directories.  The timeline is
persisted next to ``final.mp4`` and carries a stable content fingerprint so a
re-render of unchanged inputs produces an identical timeline.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from packages.pipeline_services.media_utils import get_ffmpeg_path, get_media_duration

# Matches an SRT timestamp line:  "HH:MM:SS,mmm --> HH:MM:SS,mmm"
_TS_LINE_RE = re.compile(
    r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*$"
)


def _to_ms(h: str, m: str, s: str, ms: str) -> int:
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(ms)


def _fmt_ms(total_ms: int) -> str:
    ms = total_ms % 1000
    total_s = total_ms // 1000
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def compute_scene_offset_ms(scene_path: Path | None) -> int:
    """Return the scene segment duration in ms — the AV offset for the montage.

    Returns 0 when there is no scene segment (generate mode), so the no-scene
    path shares the same offset code as the scene path (offset 0 is identity).
    """
    if scene_path is None or not Path(scene_path).exists():
        return 0
    return int(round(get_media_duration(Path(scene_path)) * 1000))


def _basename(path: str) -> str:
    """Return the final path component so fingerprints are machine-independent."""
    return Path(path).name if path else ""


def build_final_timeline(
    *,
    scene_ms: int,
    montage_segments: list[dict[str, Any]],
    scene_source: dict[str, Any] | None = None,
    aligned: bool = True,
) -> dict[str, Any]:
    """Build the authoritative Final Timeline from actual render inputs.

    *montage_segments* are the trimmed per-sentence segments (the same dicts
    fed to the base-video builder: ``visual_type``/``file_path``/``asset_id``/
    ``sentence``/``duration``).  Segments are laid out contiguously and never
    overlap; a crossfade belongs wholly to the following segment, so each
    segment's ``start_ms`` equals the previous segment's ``end_ms``.

    Returns a dict with ``segments`` (scene/montage/blank), ``duration_ms`` and
    a content ``fingerprint`` (stable across machines — hashes content and
    basenames, never absolute paths or output bytes).
    """
    segments: list[dict[str, Any]] = []
    cursor = 0

    # 1. Scene segment (only when a scene was actually rendered).
    if scene_ms > 0:
        segments.append(
            {
                "kind": "scene",
                "start_ms": 0,
                "end_ms": scene_ms,
                "sentence_index": None,
                "text": "",
                "source": scene_source or {},
            }
        )
        cursor = scene_ms

    # 2. Montage / blank segments — one per Script Sentence.
    for index, seg in enumerate(montage_segments):
        duration_ms = int(round(float(seg.get("duration", 0.0)) * 1000))
        visual_type = seg.get("visual_type", "clip")
        kind = "blank" if visual_type == "blank" else "montage"
        source: dict[str, Any] = {}
        if kind == "montage":
            if seg.get("asset_id"):
                source["asset_id"] = seg["asset_id"]
            if seg.get("file_path"):
                source["file_path"] = seg["file_path"]
        segments.append(
            {
                "kind": kind,
                "start_ms": cursor,
                "end_ms": cursor + duration_ms,
                "sentence_index": index,
                "text": seg.get("sentence", ""),
                "source": source,
            }
        )
        cursor += duration_ms

    return {
        "version": "1.0",
        "duration_ms": cursor,
        "aligned": aligned,
        "segments": segments,
        "fingerprint": _fingerprint(scene_ms, montage_segments),
    }


def _fingerprint(scene_ms: int, montage_segments: list[dict[str, Any]]) -> str:
    """Stable content fingerprint over the render inputs.

    Hashes the scene duration and, per segment, the kind/basename/trimmed
    duration/sentence — so a re-render of unchanged inputs yields an identical
    timeline while any content change is detected.  Absolute paths and output
    bytes are deliberately excluded (machine-independent).
    """
    hasher = hashlib.sha256()
    hasher.update(str(scene_ms).encode("utf-8"))
    for seg in montage_segments:
        hasher.update(str(seg.get("visual_type", "clip")).encode("utf-8"))
        hasher.update(_basename(seg.get("file_path", "")).encode("utf-8"))
        hasher.update(str(round(float(seg.get("duration", 0.0)), 3)).encode("utf-8"))
        hasher.update(seg.get("sentence", "").encode("utf-8"))
    return hasher.hexdigest()


def align_audio(
    audio_path: Path, output_path: Path, *, offset_ms: int, total_ms: int
) -> Path:
    """Offset TTS audio to the montage start and pad/trim to *total_ms*.

    ``adelay`` shifts the voice forward by *offset_ms* (the scene duration) so
    speech begins at the montage boundary; ``apad`` + ``-t`` then size the track
    to the full base-video length so ``-shortest`` in the burn step does not
    truncate the video.  With *offset_ms* == 0 (no scene) the audio is copied
    through unchanged — the no-scene path shares this code (identity offset).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if offset_ms <= 0:
        shutil.copy2(audio_path, output_path)
        return output_path
    total_s = total_ms / 1000.0
    subprocess.run(
        [
            get_ffmpeg_path(),
            "-y",
            "-i",
            str(audio_path),
            "-af",
            f"adelay={offset_ms}:all=1,apad",
            "-t",
            f"{total_s:.3f}",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return output_path


def shift_srt(srt_text: str, offset_ms: int) -> str:
    """Shift every SRT timestamp forward by *offset_ms* milliseconds.

    Only dedicated timestamp lines (``HH:MM:SS,mmm --> HH:MM:SS,mmm``) are
    shifted; sequence numbers and text lines are passed through unchanged.
    """
    if not srt_text:
        return srt_text
    if offset_ms <= 0:
        return srt_text

    out_lines: list[str] = []
    for line in srt_text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        match = _TS_LINE_RE.match(body)
        if match:
            start = _to_ms(*match.group(1, 2, 3, 4)) + offset_ms
            end = _to_ms(*match.group(5, 6, 7, 8)) + offset_ms
            out_lines.append(f"{_fmt_ms(start)} --> {_fmt_ms(end)}{ending}")
        else:
            out_lines.append(line)
    return "".join(out_lines)
