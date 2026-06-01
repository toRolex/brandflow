from __future__ import annotations

import os
import platform
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 30
THUMBNAIL_WIDTH = 220

_IS_WINDOWS = platform.system() == "Windows"

_DEFAULT_TOOLS = {
    "Darwin": {
        "FFMPEG_PATH": "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
        "FFPROBE_PATH": "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe",
    },
    "Windows": {
        "FFMPEG_PATH": "tools/bin/ffmpeg.exe",
        "FFPROBE_PATH": "tools/bin/ffprobe.exe",
    },
}


def _resolve_tool_path(path_str: str) -> str:
    """Resolve tool path: if it looks like a relative path (contains separators), make it absolute relative to CWD."""
    if "/" in path_str or "\\" in path_str:
        p = Path(path_str)
        if not p.is_absolute():
            p = Path.cwd() / p
        return str(p)
    return path_str


def _get_default(env_key: str, fallback_name: str) -> str:
    defaults = _DEFAULT_TOOLS.get(platform.system(), {})
    return os.environ.get(env_key, defaults.get(env_key, fallback_name))


class ThumbnailGenerator:
    def __init__(self, ffmpeg_path: str | None = None) -> None:
        if ffmpeg_path is None:
            ffmpeg_path = _get_default("FFMPEG_PATH", "ffmpeg")
        self.ffmpeg_path = _resolve_tool_path(ffmpeg_path)
        ffprobe_path = _get_default("FFPROBE_PATH", "ffprobe")
        self.ffprobe_path = _resolve_tool_path(ffprobe_path)

    def generate(self, video_path: Path, output_path: Path) -> bool:
        try:
            duration = self._get_duration(video_path)
            mid_time = duration / 2.0
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            cmd = [
                self.ffmpeg_path,
                "-ss", f"{mid_time:.2f}",
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", f"scale={THUMBNAIL_WIDTH}:-1,format=yuvj420p",
                "-q:v", "2",
                "-update", "1",
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
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
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