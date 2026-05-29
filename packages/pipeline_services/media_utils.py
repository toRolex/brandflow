"""Shared media helpers used across control_plane and runtime_worker."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def write_concat_file(list_path: Path, clips: list[Path]) -> None:
    list_path.parent.mkdir(parents=True, exist_ok=True)
    with list_path.open("w", encoding="utf-8") as handle:
        for clip in clips:
            handle.write(f"file '{str(clip).replace(chr(92), '/')}'\n")


def get_media_duration(file_path: Path) -> float:
    ffprobe = os.environ.get("FFPROBE_PATH", "ffprobe")
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())
