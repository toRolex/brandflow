from __future__ import annotations

import os
from pathlib import Path

from packages.runtime_adapters.base import BaseRuntimeAdapter


class WindowsProdRuntimeAdapter(BaseRuntimeAdapter):
    """Runtime adapter for the Windows production environment.

    Locates ffmpeg by probing, in order:
      1. ``FFMPEG_PATH`` environment variable
      2. ``tools/bin/ffmpeg.exe`` relative to CWD
      3. Chocolatey install path
    """

    profile_name = "windows-prod"

    _FFMPEG_CANDIDATES: tuple[str, ...] = (
        "tools/bin/ffmpeg.exe",
        "C:/ProgramData/chocolatey/bin/ffmpeg.exe",
    )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def ffmpeg_path(self) -> Path:
        """Return the resolved path to ``ffmpeg.exe``.

        Raises :class:`FileNotFoundError` if no candidate exists on disk.
        """
        env = os.environ.get("FFMPEG_PATH")
        if env is not None:
            path = Path(env)
            if path.exists():
                return path

        for candidate in self._FFMPEG_CANDIDATES:
            path = Path(candidate)
            if path.exists():
                return path

        raise FileNotFoundError(
            "ffmpeg not found. Set FFMPEG_PATH env var, add tools/bin/ffmpeg.exe, "
            "or install via Chocolatey"
        )

    def ensure_tools(self) -> None:
        return None

    def attempt_root(self, workspace_root: Path, attempt_id: str) -> Path:
        root = workspace_root / "attempts" / attempt_id
        root.mkdir(parents=True, exist_ok=True)
        return root

    def build_fake_outputs(self, attempt_root: Path) -> list[Path]:
        output_root = attempt_root / "output"
        output_root.mkdir(parents=True, exist_ok=True)
        files = {
            "script.json": b"{}\n",
            "audio.mp3": b"stub-audio",
            "subtitles.srt": b"1\n00:00:00,000 --> 00:00:01,000\nstub\n",
            "final.mp4": b"stub-video",
        }
        paths: list[Path] = []
        for name, content in files.items():
            path = output_root / name
            path.write_bytes(content)
            paths.append(path)
        return paths
