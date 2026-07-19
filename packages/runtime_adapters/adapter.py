from __future__ import annotations

from pathlib import Path

from packages.pipeline_services.media_utils import _resolve_ffmpeg_path


class RuntimeAdapter:
    """Runtime adapter for the current platform environment.

    Locates ffmpeg using the shared resolver:
      1. ``FFMPEG_PATH`` environment variable
      2. ``tools/bin/ffmpeg`` (``tools/bin/ffmpeg.exe`` on Windows) relative to CWD
      3. ``shutil.which('ffmpeg')`` (system PATH)
    """

    def __init__(self, profile_name: str = "mac-local") -> None:
        self.profile_name = profile_name

    def ensure_tools(self) -> None:
        return None

    def ffmpeg_path(self) -> Path:
        """Return the resolved path to ffmpeg.

        Raises :class:`FileNotFoundError` if ffmpeg cannot be located.
        """
        return Path(_resolve_ffmpeg_path())

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
