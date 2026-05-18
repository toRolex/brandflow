from __future__ import annotations

from pathlib import Path

from packages.runtime_adapters.base import BaseRuntimeAdapter


class MacLocalRuntimeAdapter(BaseRuntimeAdapter):
    profile_name = "mac-local"

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
