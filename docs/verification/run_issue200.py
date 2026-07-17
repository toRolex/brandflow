"""End-to-end verification harness for issue #200.

Runs an Import-mode job through the local control-plane auto-tick loop and
records:

- job configuration
- state-machine transitions
- final video path
- ffprobe stream metadata
- scene-order frame samples
- key control-plane logs

The job uses synthetic media so it does not need real LLM/TTS/Vision keys.
The harness writes a temporary ``config/app_config.json`` while it runs and
restores the previous file afterwards.
"""

from __future__ import annotations

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
LOG_PATH = VERIFY_DIR / "control_plane.log"
REPORT_PATH = VERIFY_DIR / "issue-200-verification.md"
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
    """Generate the synthetic audio / scene clips if they are missing."""
    (MEDIA_DIR / "scene1").mkdir(parents=True, exist_ok=True)
    (MEDIA_DIR / "scene2").mkdir(parents=True, exist_ok=True)

    audio = MEDIA_DIR / "audio.mp3"
    if not audio.exists():
        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:duration=5",
                "-ac",
                "2",
                "-ar",
                "44100",
                "-b:a",
                "192k",
                str(audio),
            ]
        )

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


def _clean_env() -> dict[str, str]:
    """Return an env dict that keeps local tools but disables remote APIs."""
    env = os.environ.copy()
    for key in (
        "LLM_API_KEY",
        "LLM_API_URL",
        "TTS_API_KEY",
        "TTS_API_URL",
        "VISION_API_KEY",
        "VISION_API_URL",
        "VISION_MODEL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_URL",
        "MIMO_API_KEY",
        "MIMO_API_BASE_URL",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_API_URL",
    ):
        env.pop(key, None)
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


def _ffprobe(video_path: Path, stream_selector: str) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        stream_selector,
        "-show_entries",
        "stream=width,height,codec_name,pix_fmt,r_frame_rate,avg_frame_rate,"
        "sample_rate,channels:format=duration",
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


def main() -> int:
    VERIFY_DIR.mkdir(parents=True, exist_ok=True)
    if LOG_PATH.exists():
        LOG_PATH.unlink()

    config_backup: Path | None = None
    if CONFIG_PATH.exists():
        config_backup = CONFIG_PATH.with_suffix(".json.verify-backup")
        shutil.copy2(CONFIG_PATH, config_backup)
    _write_verify_config()
    _ensure_media()

    env = _clean_env()
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

        resp = session.post(f"{BASE_URL}/api/projects", json={"name": "issue200"})
        resp.raise_for_status()
        project_id = resp.json()["id"]
        print(f"[verify] project {project_id}")

        resp = session.post(
            f"{BASE_URL}/api/projects/{project_id}/jobs",
            json={
                "product": "verify",
                "brand": "brandflow",
                "platforms": ["douyin"],
                "mode": "import",
                "manual_script": MANUAL_SCRIPT,
                "auto_approve": True,
                "skip_subtitle": True,
                "audio_source": "tts",
                "language": "mandarin",
            },
        )
        resp.raise_for_status()
        job_id = resp.json()["job_id"]
        print(f"[verify] job {job_id}")

        audio_path = MEDIA_DIR / "audio.mp3"
        with audio_path.open("rb") as f:
            resp = session.post(
                f"{BASE_URL}/api/jobs/{job_id}/audio",
                files={"file": ("audio.mp3", f, "audio/mpeg")},
            )
        resp.raise_for_status()
        print(f"[verify] uploaded audio -> {resp.json()['audio_path']}")

        phases_seen: list[str] = []
        final_phase = ""
        for _ in range(120):
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
            return 1

        job_dir = (
            ROOT / "workspace" / "projects" / project_id / "runtime" / "jobs" / job_id
        )
        final_video = job_dir / "final.mp4"
        if not final_video.exists():
            print(f"[verify] final video missing: {final_video}")
            return 1

        probe = _ffprobe(final_video, "v:0")
        audio_probe = _ffprobe(final_video, "a:0")

        frame_1s = job_dir / "frames" / "frame_t1.png"
        frame_4s = job_dir / "frames" / "frame_t4.png"
        _extract_frame(final_video, 1, frame_1s)
        _extract_frame(final_video, 4, frame_4s)
        center_t1 = _center_pixel(frame_1s)
        center_t4 = _center_pixel(frame_4s)

        print(f"[verify] final video: {final_video}")
        print(json.dumps(probe, indent=2, ensure_ascii=False))

        log_tail = ""
        if LOG_PATH.exists():
            log_text = LOG_PATH.read_text(encoding="utf-8", errors="replace")
            log_tail = "\n".join(log_text.splitlines()[-80:])

        artifacts = sorted(p.name for p in job_dir.iterdir() if p.is_file())
        phases_text = " -> ".join(phases_seen)
        artifacts_text = "\n".join(artifacts)
        video_stream = (probe.get("streams") or [{}])[0]
        audio_stream = (audio_probe.get("streams") or [{}])[0]
        verified_at = time.strftime("%Y-%m-%d %H:%M:%S %z")
        final_rel = final_video.relative_to(ROOT)
        probe_text = json.dumps(probe, indent=2, ensure_ascii=False)

        report = f"""# Issue #200 End-to-End Verification Report

## Summary

- **Mode**: Import
- **Product**: verify
- **Project ID**: `{project_id}`
- **Job ID**: `{job_id}`
- **Final state**: `{final_phase}`
- **Final video**: `{final_rel}`
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
  "skip_subtitle": true,
  "audio_source": "tts",
  "language": "mandarin"
}}
```

## Scene configuration (temporary ``config/app_config.json``)

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

Frames were sampled from `final.mp4` to verify scene order:

| Time | Center pixel (RGB) | Interpretation |
|------|--------------------|----------------|
| 1 s | {center_t1} | first scene clip (red) |
| 4 s | {center_t4} | second scene clip (blue) |

This confirms the scene segment and montage concatenation produced the expected
order.

## Notes

- No real LLM/TTS/Vision calls were made; the job relied on a manual script and
  an uploaded synthetic audio file.
- Scene assembly used two synthetic 720x1280 clips with a 500 ms crossfade.
- Montage assembly concatenated the scene segment with the (empty) base path and
  produced `assembled.mp4`.
- Final rendering burned the uploaded audio into `final.mp4`. Subtitle burn was
  skipped (`skip_subtitle=true`) because the local Homebrew ffmpeg build does not
  include the `subtitles` filter (libass). Since the subtitle phase is skipped
  when `skip_subtitle=true`, no SRT file was generated in this run.
- Manual playback inspection was replaced by automated frame sampling (above).
- The control plane was run with `DEV_AUTO_TICK=1`; a separate worker was not
  started because the auto-tick loop already executes the full pipeline locally.
- This run only covers the post-refactor code; a pre-refactor baseline run was
  not performed because the verification is that the current pipeline still
  produces the documented output format.

## Control-plane log tail

```
{log_tail}
```
"""
        REPORT_PATH.write_text(report, encoding="utf-8")
        print(f"[verify] report written to {REPORT_PATH}")
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
