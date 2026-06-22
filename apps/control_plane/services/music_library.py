from __future__ import annotations

import subprocess
from pathlib import Path


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".aac", ".m4a"}


class MusicLibrary:
    """Scans workspace/music_library/ for audio files and caches metadata."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._tracks: list[dict] = []
        self._scan()

    def _scan(self) -> None:
        music_dir = self._root_dir / "workspace" / "music_library"
        music_dir.mkdir(parents=True, exist_ok=True)
        tracks: list[dict] = []
        for f in sorted(music_dir.iterdir()):
            if not f.is_file():
                continue
            suffix = f.suffix.lower()
            if suffix not in AUDIO_EXTENSIONS:
                continue
            duration = self._probe_duration(f)
            rel = f.relative_to(self._root_dir).as_posix()
            tracks.append({
                "filename": f.name,
                "relative_path": rel,
                "duration_seconds": duration,
                "size_bytes": f.stat().st_size,
            })
        self._tracks = tracks

    @staticmethod
    def _probe_duration(path: Path) -> float | None:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception:
            pass
        return None

    @property
    def tracks(self) -> list[dict]:
        return list(self._tracks)
