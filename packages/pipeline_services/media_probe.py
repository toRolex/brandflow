"""Small ffprobe boundary shared by export packaging and validation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TypedDict

from packages.pipeline_services.media_utils import get_ffmpeg_path, get_ffprobe_path


class MediaInfo(TypedDict):
    duration: float | None
    video_codec: str | None
    audio_codec: str | None


def probe_media(path: Path) -> MediaInfo:
    """Return duration and first audio/video codecs, or empty facts on failure."""
    try:
        result = subprocess.run(
            [
                get_ffprobe_path(),
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type,codec_name",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        payload = json.loads(result.stdout)
        streams = payload.get("streams", [])
        duration_raw = payload.get("format", {}).get("duration")
        return {
            "duration": float(duration_raw) if duration_raw is not None else None,
            "video_codec": next(
                (
                    stream.get("codec_name")
                    for stream in streams
                    if stream.get("codec_type") == "video"
                ),
                None,
            ),
            "audio_codec": next(
                (
                    stream.get("codec_name")
                    for stream in streams
                    if stream.get("codec_type") == "audio"
                ),
                None,
            ),
        }
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError):
        return {"duration": None, "video_codec": None, "audio_codec": None}


def is_decodable_video(path: Path) -> bool:
    """Return whether FFmpeg can decode the complete primary video stream."""
    try:
        subprocess.run(
            [
                get_ffmpeg_path(),
                "-v",
                "error",
                "-xerror",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-f",
                "null",
                "-",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False
