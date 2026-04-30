from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime
from pathlib import Path


def resolve_tool(root: Path, env_key: str, relative: str) -> Path:
    configured = os.getenv(env_key, "").strip()
    if configured:
        return Path(configured)
    return root / relative


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a 300-second local mock project for delivery validation.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--name", default="", help="Project name")
    parser.add_argument("--duration", type=int, default=300, help="Mock source duration in seconds")
    parser.add_argument("--size", default="720x1280", help="Video size, default 720x1280")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    ffmpeg = resolve_tool(root, "FFMPEG_PATH", "tools/bin/ffmpeg.exe")
    if not ffmpeg.exists():
        raise FileNotFoundError(f"Missing ffmpeg: {ffmpeg}")

    project_name = args.name.strip() or f"001mock_acceptance_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    project_dir = root / project_name
    raw_dir = project_dir / "原素材"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output = raw_dir / "source_300s.mp4"

    if not output.exists():
        cmd = [
            str(ffmpeg),
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={args.size}:rate=25",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(args.duration),
            "-shortest",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "32",
            "-g",
            "125",
            "-keyint_min",
            "125",
            "-sc_threshold",
            "0",
            "-force_key_frames",
            "expr:gte(t,n_forced*5)",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            "-y",
            str(output),
        ]
        subprocess.run(cmd, check=True)

    print(project_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
