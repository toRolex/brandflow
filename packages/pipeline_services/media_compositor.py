"""MediaCompositor — thin ffmpeg composition primitives.

Encapsulates the two ffmpeg subprocess calls previously inlined in
``PhaseOrchestrator``:

* ``concat_two``    — normalize + concatenate two video files.
* ``crossfade_scene`` — chain xfade transitions across multiple clips.

File existence checks and fallback logic stay in the orchestrator handlers;
this module only composes the ffmpeg command and runs it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from packages.pipeline_services.media_utils import (
    get_ffmpeg_path,
    get_media_duration,
)


# Vertical 720p output spec used across the pipeline.
_WIDTH = 720
_HEIGHT = 1280
_FPS = 30
_PIX_FMT = "yuv420p"
_VIDEO_CODEC = "libx264"
_PRESET = "ultrafast"
_CRF = "23"


def _normalize_filter(label_in: str, label_out: str) -> str:
    """Return a filter normalizing one video stream to the target spec."""
    return (
        f"[{label_in}:v]settb=AVTB,fps={_FPS},"
        f"scale={_WIDTH}:{_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={_WIDTH}:{_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
        f"format=pix_fmts={_PIX_FMT}[{label_out}]"
    )


class MediaCompositor:
    """Minimal ffmpeg composition wrapper."""

    @staticmethod
    def concat_two(first: Path, second: Path, out: Path) -> Path:
        """Normalize and concatenate two video files into *out*.

        Returns *out* path on success.
        """
        out.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg = get_ffmpeg_path()
        filter_complex = (
            f"{_normalize_filter('0', 'v0')};"
            f"{_normalize_filter('1', 'v1')};"
            "[v0][v1]concat=n=2:v=1:a=0"
        )
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(first),
            "-i",
            str(second),
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-an",
            "-c:v",
            _VIDEO_CODEC,
            "-preset",
            _PRESET,
            "-crf",
            _CRF,
            "-pix_fmt",
            _PIX_FMT,
            "-movflags",
            "+faststart",
            str(out),
        ]
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        return out

    @staticmethod
    def crossfade_scene(
        clips: list[Path], out: Path, transition_duration: float
    ) -> Path:
        """Build a crossfade scene segment from *clips*.

        A single clip is copied directly.  Two or more clips are normalized and
        chained with ``xfade`` transitions.

        Returns *out* path on success.
        """
        out.parent.mkdir(parents=True, exist_ok=True)
        if len(clips) == 1:
            shutil.copy2(clips[0], out)
            return out

        ffmpeg = get_ffmpeg_path()
        durations = [get_media_duration(c) for c in clips]

        filter_parts: list[str] = []
        accumulated = durations[0]
        for i in range(1, len(clips)):
            offset = accumulated - transition_duration
            prev_label = f"r{i - 1}" if i > 1 else "c0"
            cur_in_label = f"c{i}"
            out_label = f"t{i}"

            filter_parts.append(_normalize_filter(str(i), cur_in_label))
            filter_parts.append(
                f"[{prev_label}][{cur_in_label}]"
                f"xfade=transition=fade:duration={transition_duration:.3f}:"
                f"offset={offset:.3f}[{out_label}]"
            )
            if i < len(clips) - 1:
                filter_parts.append(
                    f"[{out_label}]setpts=PTS-STARTPTS,fps={_FPS}[r{i}]"
                )

            accumulated += durations[i] - transition_duration

        filter_complex = _normalize_filter("0", "c0") + ";" + ";".join(filter_parts)
        final_label = f"t{len(clips) - 1}"

        cmd = [ffmpeg, "-y"]
        for clip in clips:
            cmd.extend(["-i", str(clip)])
        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{final_label}]",
                "-an",
                "-c:v",
                _VIDEO_CODEC,
                "-preset",
                _PRESET,
                "-crf",
                _CRF,
                "-pix_fmt",
                _PIX_FMT,
                "-movflags",
                "+faststart",
                str(out),
            ]
        )

        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        return out
