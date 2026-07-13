from __future__ import annotations

import subprocess
import logging
from pathlib import Path

from packages.pipeline_services.media_utils import (
    _resolve_ffmpeg_path,
    _resolve_ffprobe_path,
)

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 30
THUMBNAIL_WIDTH = 220


class ThumbnailGenerator:
    def __init__(
        self, ffmpeg_path: str | None = None, ffprobe_path: str | None = None
    ) -> None:
        self.ffmpeg_path = (
            ffmpeg_path if ffmpeg_path is not None else _resolve_ffmpeg_path()
        )
        self.ffprobe_path = (
            ffprobe_path if ffprobe_path is not None else _resolve_ffprobe_path()
        )

    def generate(self, video_path: Path, output_path: Path) -> bool:
        try:
            duration = self._get_duration(video_path)
            mid_time = duration / 2.0

            output_path.parent.mkdir(parents=True, exist_ok=True)

            cmd = [
                self.ffmpeg_path,
                "-ss",
                f"{mid_time:.2f}",
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-vf",
                f"scale={THUMBNAIL_WIDTH}:-1,format=yuvj420p",
                "-q:v",
                "2",
                "-update",
                "1",
                "-y",
                str(output_path),
            ]

            subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=FFMPEG_TIMEOUT,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to generate thumbnail for {video_path}: {e}")
            return False

    def _get_duration(self, video_path: Path) -> float:
        cmd = [
            self.ffprobe_path,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=FFMPEG_TIMEOUT,
        )
        return float(result.stdout.strip())
