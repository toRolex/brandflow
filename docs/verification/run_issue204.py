"""End-to-end verification harness for issue #204.

Runs an Import-mode job through the local control-plane auto-tick loop with
real TTS synthesis and subtitle burn (no shortcuts), records all artifacts
and ffprobe metadata.

Usage:
    uv run python docs/verification/run_issue204.py --run-label v0.7.10
    uv run python docs/verification/run_issue204.py --run-label develop

Each run produces docs/verification/issue-204-verification-{run-label}.md.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
BASE_URL = "http://127.0.0.1:17890"
VERIFY_DIR = ROOT / "docs" / "verification"
LOG_PATH = VERIFY_DIR / "control_plane_issue204.log"
CONFIG_PATH = ROOT / "config" / "app_config.json"
MEDIA_DIR = ROOT / "workspace" / "verify"

MANUAL_SCRIPT = (
    "欢迎观看本期测评。这款产品做工扎实。使用体验非常流畅。推荐立即下单体验。"
)

VERIFY_CONFIG = {
    "active_product_id": "verify",
    "products": [
        {
            "id": "verify",
            "name": "verify",
            "default_name": "verify",
            "default_brand": "brandflow",
            "scene": {
                "folders": [
                    {"path": "verify/scene1"},
                    {"path": "verify/scene2"},
                ],
                "transition_duration_ms": 500,
            },
        }
    ],
    "media": {
        "ffmpeg_path": "ffmpeg",
        "ffprobe_path": "ffprobe",
        "subtitle_mode": "script_timed",
    },
}


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def _ensure_media() -> None:
    """Generate synthetic scene clips if they are missing."""
    (MEDIA_DIR / "scene1").mkdir(parents=True, exist_ok=True)
    (MEDIA_DIR / "scene2").mkdir(parents=True, exist_ok=True)

    for name, color in (("scene1", "red"), ("scene2", "blue")):
        clip = MEDIA_DIR / name / f"{name}.mp4"
        if not clip.exists():
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    f"color=c={color}:s=720x1280:d=3",
                    "-r",
                    "30",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:v",
                    "libx264",
                    str(clip),
                ]
            )


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["DEV_AUTO_TICK"] = "1"
    env["CONTROL_PLANE_HOST"] = "127.0.0.1"
    env["CONTROL_PLANE_PORT"] = "17890"
    return env


def _wait_for_health(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{BASE_URL}/api/health", timeout=2)
            if resp.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    raise RuntimeError("control plane did not become healthy")


def _ffprobe(video_path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=width,height,codec_name,pix_fmt,r_frame_rate,avg_frame_rate,"
        "sample_rate,channels:format=duration,size,bit_rate",
        "-of",
        "json",
        str(video_path),
    ]
    result = _run(cmd)
    return json.loads(result.stdout)


def _extract_frame(video_path: Path, timestamp: int, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(timestamp),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            str(out_path),
        ]
    )


def _center_pixel(image_path: Path) -> tuple[int, int, int]:
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    return img.getpixel((img.width // 2, img.height // 2))


def _write_verify_config() -> None:
    CONFIG_PATH.write_text(
        json.dumps(VERIFY_CONFIG, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _check_subtitle_filter() -> bool:
    result = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True)
    return "subtitles" in result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-label", required=True, help="e.g. v0.7.10 or develop")
    args = parser.parse_args()
    label = args.run_label
    report_path = VERIFY_DIR / f"issue-204-verification-{label}.md"

    VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    if LOG_PATH.exists():
        LOG_PATH.unlink()

    config_backup: Path | None = None
    if CONFIG_PATH.exists():
        config_backup = CONFIG_PATH.with_suffix(".json.issue204-backup")
        shutil.copy2(CONFIG_PATH, config_backup)
    _write_verify_config()
    _ensure_media()

    subtitle_support = _check_subtitle_filter()
    print(f"[verify] ffmpeg subtitles filter: {'YES' if subtitle_support else 'NO'}")

    env = _env()
    server = subprocess.Popen(
        [sys.executable, "-m", "apps.control_plane"],
        cwd=ROOT,
        env=env,
        stdout=open(LOG_PATH, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
    )

    try:
        _wait_for_health()
        print("[verify] control plane healthy")

        session = requests.Session()

        # Create project
        resp = session.post(f"{BASE_URL}/api/projects", json={"name": "issue204"})
        resp.raise_for_status()
        project_id = resp.json()["id"]
        print(f"[verify] project {project_id}")

        # Create job — Import mode, real TTS, no skip_subtitle
        resp = session.post(
            f"{BASE_URL}/api/projects/{project_id}/jobs",
            json={
                "product": "verify",
                "brand": "brandflow",
                "platforms": ["douyin"],
                "mode": "import",
                "manual_script": MANUAL_SCRIPT,
                "auto_approve": True,
                "audio_source": "tts",
                "language": "mandarin",
            },
        )
        resp.raise_for_status()
        job_id = resp.json()["job_id"]
        print(f"[verify] job {job_id}")

        # Wait for completion
        phases_seen: list[str] = []
        final_phase = ""
        for _ in range(300):  # 10 min max (TTS is slow)
            resp = session.get(f"{BASE_URL}/api/jobs/{job_id}")
            resp.raise_for_status()
            data = resp.json()
            phase = data.get("phase", "")
            if phase != (phases_seen[-1] if phases_seen else ""):
                phases_seen.append(phase)
                print(f"[verify] phase -> {phase}")
            if phase in ("completed", "failed"):
                final_phase = phase
                break
            time.sleep(2)

        if final_phase != "completed":
            print(f"[verify] job ended in {final_phase}")
            # Dump job state for debugging
            print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
            return 1

        # Collect artifacts
        job_dir = (
            ROOT / "workspace" / "projects" / project_id / "runtime" / "jobs" / job_id
        )
        final_video = job_dir / "final.mp4"
        if not final_video.exists():
            print(f"[verify] final video missing: {final_video}")
            return 1

        # ffprobe the final video
        probe = _ffprobe(final_video)

        # Extract frame samples for scene order check
        frame_1s = job_dir / "frames" / "frame_t1.png"
        frame_4s = job_dir / "frames" / "frame_t4.png"
        _extract_frame(final_video, 1, frame_1s)
        _extract_frame(final_video, 4, frame_4s)
        center_t1 = _center_pixel(frame_1s)
        center_t4 = _center_pixel(frame_4s)

        print(f"[verify] final video: {final_video}")
        print(f"[verify] file size: {final_video.stat().st_size} bytes")
        print(json.dumps(probe, indent=2, ensure_ascii=False))

        # Collect logs
        log_tail = ""
        if LOG_PATH.exists():
            log_text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
            log_tail = "\n".join(log_text.splitlines()[-80:])

        artifacts = sorted(p.name for p in job_dir.iterdir() if p.is_file())
        phases_text = " -> ".join(phases_seen)
        artifacts_text = "\n".join(artifacts)
        video_stream = next(
            (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
            probe.get("streams", [{}])[0],
        )
        audio_streams = [
            s for s in probe.get("streams", []) if s.get("codec_type") == "audio"
        ]
        audio_stream = audio_streams[0] if audio_streams else {}
        file_size = final_video.stat().st_size
        verified_at = time.strftime("%Y-%m-%d %H:%M:%S %z")
        final_rel = final_video.relative_to(ROOT)
        probe_text = json.dumps(probe, indent=2, ensure_ascii=False)

        report = f"""# Issue #204 End-to-End Verification Report — Run: {label}

## Summary

- **Mode**: Import
- **Run label**: {label}
- **Product**: verify
- **Project ID**: `{project_id}`
- **Job ID**: `{job_id}`
- **Final state**: `{final_phase}`
- **Final video**: `{final_rel}`
- **File size**: {file_size} bytes
- **ffmpeg subtitles filter**: {"YES" if subtitle_support else "NO"}
- **Verified at**: {verified_at}

## Job configuration

```json
{{
  "product": "verify",
  "brand": "brandflow",
  "platforms": ["douyin"],
  "mode": "import",
  "manual_script": "{MANUAL_SCRIPT}",
  "auto_approve": true,
  "audio_source": "tts",
  "language": "mandarin"
}}
```

## Scene configuration

```json
{json.dumps(VERIFY_CONFIG["products"][0]["scene"], ensure_ascii=False, indent=2)}
```

## State-machine phases observed

```
{phases_text}
```

## Artifacts in job directory

```
{artifacts_text}
```

## ffprobe output (final.mp4)

```json
{probe_text}
```

## Format check

| Field | Expected | Actual |
|-------|----------|--------|
| width | 720 | {video_stream.get("width", "N/A")} |
| height | 1280 | {video_stream.get("height", "N/A")} |
| codec | libx264 (h264) | {video_stream.get("codec_name", "N/A")} |
| pix_fmt | yuv420p | {video_stream.get("pix_fmt", "N/A")} |
| fps | 30 | {video_stream.get("avg_frame_rate", "N/A")} |
| audio | AAC | {audio_stream.get("codec_name", "N/A")} |

## Scene / montage order check

| Time | Center pixel (RGB) | Interpretation |
|------|--------------------|----------------|
| 1 s | {center_t1} | first scene clip (red) |
| 4 s | {center_t4} | second scene clip (blue) |

## Control-plane log tail

```
{log_tail}
```
"""
        report_path.write_text(report, encoding="utf-8")
        print(f"[verify] report written to {report_path}")
        return 0

    finally:
        if server.poll() is None:
            server.send_signal(signal.SIGTERM)
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
        if config_backup is not None:
            shutil.move(str(config_backup), CONFIG_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
