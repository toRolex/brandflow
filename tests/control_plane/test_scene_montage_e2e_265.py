"""Single Control-Plane end-to-end HTTP flow for Scene + Montage composition (#265).

These tests lock the post-review backend flow that #264 landed: after the
``asset_review`` gate is approved over HTTP, ``montage_assembling`` builds the
independent Montage Segment and ``video_rendering`` composes the base video
from that segment (plus an optional Scene Segment in import mode) — without
first constructing the review montage or reading the mutable working selection.

The assertions target *persisted* Job state (phase, execution, failed_phase)
and *runtime artifacts* on disk, not internal function call order (AC-7).  The
happy-path tests exercise real FFmpeg so the montage/scene composition is
actually rendered end-to-end; the structured-failure test needs no media tools.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app, create_orchestrator
from packages.file_store.repository import FileStoreRepository
from packages.pipeline_services.job_tick_service import JobTickService
from packages.pipeline_services.media_utils import get_media_duration

PROJECT_ID = "prj_001"
SKIP_REAL = not shutil.which("ffmpeg") or not shutil.which("ffprobe")
REAL_REASON = "ffmpeg or ffprobe not available"


# ---------------------------------------------------------------------------
# Media + path helpers (test-only)
# ---------------------------------------------------------------------------


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def _make_video(output: Path, duration: float, color: str) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s=720x1280:d={duration}:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _make_audio(output: Path, duration: float, freq: int = 440) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:duration={duration}",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return output


def _control_job_path(root: Path, job_id: str) -> Path:
    return (
        root
        / "workspace"
        / "projects"
        / PROJECT_ID
        / "control"
        / "jobs"
        / f"{job_id}.json"
    )


def _runtime_job_dir(root: Path, job_id: str) -> Path:
    return root / "workspace" / "projects" / PROJECT_ID / "runtime" / "jobs" / job_id


def _load_control_job(root: Path, job_id: str) -> dict:
    return json.loads(_control_job_path(root, job_id).read_text(encoding="utf-8"))


def _write_control_job(root: Path, job_id: str, data: dict) -> None:
    _control_job_path(root, job_id).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _make_tick_service(client: TestClient, root: Path) -> JobTickService:
    """Build a JobTickService from the app's real orchestrator + config reader."""
    repo = FileStoreRepository(root)
    orchestrator = create_orchestrator(root, client.app.state.config_reader)
    return JobTickService(
        orchestrator, repo, config_reader=client.app.state.config_reader
    )


def _drive_to_completion(
    client: TestClient,
    root: Path,
    job_id: str,
    *,
    max_ticks: int = 20,
) -> dict:
    """Tick the job forward, HTTP-approving human review gates, until terminal.

    Returns the final persisted control-plane Job dict.  Human gates
    (``final_review``) are approved over the real HTTP endpoint so the whole
    single Control-Plane flow is exercised.  ``asset_review`` is expected to be
    approved by the caller before driving.
    """
    svc = _make_tick_service(client, root)
    project_dir = root / "workspace" / "projects" / PROJECT_ID
    terminal = {"completed", "failed", "cancelled", "migration_required"}

    for _ in range(max_ticks):
        data = _load_control_job(root, job_id)
        phase = data["phase"]
        if phase in terminal:
            return data
        if phase in ("final_review", "script_review", "tts_review", "asset_review"):
            resp = client.post(
                f"/api/reviews/{job_id}/approve",
                json={"review_gate": phase, "force": True},
            )
            assert resp.status_code == 200, resp.text
            continue
        svc.tick(
            PROJECT_ID,
            job_id,
            data.get("product", "test"),
            root_dir=root,
            project_dir=project_dir,
        )
    return _load_control_job(root, job_id)


def _seed_reviewed_montage_inputs(
    job_dir: Path,
    *,
    clip_path: Path | None,
    audio: Path,
    sentence_text: str = "第一句介绍产品。",
    duration: float = 3.0,
) -> None:
    """Write the runtime inputs montage_assembling consumes after asset review.

    ``selected_clips.json`` is the pre-approval working selection; the HTTP
    approve endpoint freezes it into the immutable ``reviewed_assets.json``
    snapshot.  A ``clip_path`` of ``None`` produces a blank (black-frame)
    montage segment.
    """
    job_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(audio, job_dir / "audio.mp3")
    if clip_path is None:
        clip = {
            "sentence": sentence_text,
            "category": "intro",
            "file_path": "",
            "asset_id": "",
            "duration_seconds": duration,
            "method": "blank",
            "visual_type": "blank",
        }
    else:
        clip = {
            "sentence": sentence_text,
            "category": "intro",
            "file_path": str(clip_path),
            "asset_id": "a1",
            "duration_seconds": duration,
            "method": "llm_match",
            "visual_type": "clip",
        }
    (job_dir / "selected_clips.json").write_text(
        json.dumps([clip], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (job_dir / "sentences.json").write_text(
        json.dumps(
            [
                {
                    "index": 0,
                    "text": sentence_text,
                    "start_seconds": 0.0,
                    "end_seconds": duration,
                    "model": "",
                    "voice": "",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (job_dir / "subtitles.srt").write_text(
        f"1\n00:00:00,000 --> 00:00:0{int(duration)},000\n{sentence_text}\n",
        encoding="utf-8",
    )
    # Script text so any downstream discovery has a source.
    (job_dir / "test口播文案.txt").write_text(sentence_text, encoding="utf-8")


def _create_job_at_asset_review(
    client: TestClient,
    root: Path,
    *,
    mode: str,
    scene_folder_ids: list[str] | None = None,
) -> str:
    """Create a job over HTTP, then move it to the asset_review gate on disk."""
    body: dict = {
        "product": "test",
        "platforms": ["douyin"],
        "mode": mode,
        "manual_script": "第一句介绍产品。",
    }
    if scene_folder_ids is not None:
        body["scene_folder_ids"] = scene_folder_ids
    resp = client.post(f"/api/projects/{PROJECT_ID}/jobs", json=body)
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    data = _load_control_job(root, job_id)
    data["phase"] = "asset_review"
    data["review_status"] = "pending"
    _write_control_job(root, job_id, data)
    return job_id


def _configure_scene_folder(root: Path, name: str, rel_path: str) -> Path:
    """Register a scene folder in app_config.json and create it on disk."""
    config_dir = root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "app_config.json"
    config = (
        json.loads(config_path.read_text(encoding="utf-8"))
        if config_path.exists()
        else {}
    )
    scene = config.setdefault("scene", {"folders": [], "transition_duration_ms": 500})
    scene.setdefault("folders", []).append({"name": name, "path": rel_path})
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    folder = root / "workspace" / rel_path
    folder.mkdir(parents=True, exist_ok=True)
    # Import-mode job creation validates the folder holds a usable video file
    # (SCENE_MEDIA_MISSING otherwise); a real clip also lets scene selection
    # succeed if the pipeline ever re-runs scene_assembling.
    _make_video(folder / "clip.mp4", 2.0, "red")
    return folder


# ---------------------------------------------------------------------------
# 1. Generate mode: asset_review approval → montage → video_rendering → done
# ---------------------------------------------------------------------------


@pytest.mark.skipif(SKIP_REAL, reason=REAL_REASON)
def test_generate_job_asset_review_to_video_rendering_completes_via_http(
    tmp_path: Path,
) -> None:
    """Generate mode uses the Montage Segment (no Scene Segment) to build the
    base video: after HTTP asset_review approval the job assembles the montage,
    enters and completes video_rendering, and reaches completed — never
    ``asset_review → montage_assembling → failed`` (AC-1, 3, 5, 8)."""
    root = tmp_path
    client = TestClient(create_app(root))

    job_id = _create_job_at_asset_review(client, root, mode="generate")
    job_dir = _runtime_job_dir(root, job_id)
    audio = _make_audio(job_dir / "_tts.wav", 3.0)
    # Blank montage segment — generate mode needs no Scene Segment.
    _seed_reviewed_montage_inputs(job_dir, clip_path=None, audio=audio)

    # Approve the asset_review gate over HTTP — this freezes reviewed_assets.json.
    resp = client.post(
        f"/api/reviews/{job_id}/approve",
        json={"review_gate": "asset_review", "force": True},
    )
    assert resp.status_code == 200, resp.text
    assert (job_dir / "reviewed_assets.json").exists()

    final = _drive_to_completion(client, root, job_id)

    # Persisted phase / execution / failed_phase (AC-7).
    assert final["phase"] == "completed"
    assert final["execution"]["status"] == "succeeded"
    assert final["failed_phase"] is None

    # Runtime artifacts: montage segment was built, base video composed from it.
    assert (job_dir / "montage_segment.mp4").exists()
    assert (job_dir / "base.mp4").exists()

    # No Scene Segment in generate mode → base equals the montage layout.
    assert not (job_dir / "scene_segment.mp4").exists()
    timeline = json.loads((job_dir / "final_timeline.json").read_text("utf-8"))
    assert all(seg["kind"] != "scene" for seg in timeline["segments"])
    assert timeline["segments"][0]["start_ms"] == 0

    kinds = {a["kind"] for a in final["artifacts"]}
    assert "montage_segment" in kinds
    assert "video_base" in kinds


# ---------------------------------------------------------------------------
# 2. Import mode: Scene Segment + Montage Segment composed into the base video
# ---------------------------------------------------------------------------


@pytest.mark.skipif(SKIP_REAL, reason=REAL_REASON)
def test_import_job_base_video_contains_scene_and_montage_via_http(
    tmp_path: Path,
) -> None:
    """Import mode composes the optional Scene Segment before the Montage
    Segment in the correct order, with the two phases kept separate: the final
    base video's duration and timeline cover both scene and montage (AC-2, 6)."""
    root = tmp_path
    _configure_scene_folder(root, "场景一", "scenes/one")
    client = TestClient(create_app(root))

    job_id = _create_job_at_asset_review(
        client, root, mode="import", scene_folder_ids=["scenes/one"]
    )
    job_dir = _runtime_job_dir(root, job_id)

    # scene = 2s red segment already produced by scene_assembling (import mode).
    _make_video(job_dir / "scene_segment.mp4", 2.0, "red")
    # montage source clip = 5s blue, trimmed to ~3s in montage_assembling.
    clip_src = _make_video(job_dir / "_clip_src.mp4", 5.0, "blue")
    audio = _make_audio(job_dir / "_tts.wav", 3.0)
    _seed_reviewed_montage_inputs(job_dir, clip_path=clip_src, audio=audio)

    resp = client.post(
        f"/api/reviews/{job_id}/approve",
        json={"review_gate": "asset_review", "force": True},
    )
    assert resp.status_code == 200, resp.text

    final = _drive_to_completion(client, root, job_id)

    assert final["phase"] == "completed"
    assert final["execution"]["status"] == "succeeded"
    assert final["failed_phase"] is None

    # Both segments were produced by their own phases and survive on disk.
    assert (job_dir / "scene_segment.mp4").exists()
    assert (job_dir / "montage_segment.mp4").exists()
    assert (job_dir / "base.mp4").exists()

    # Base video duration ≈ scene(2s) + montage(~3s) → both are present.
    base_ms = get_media_duration(job_dir / "base.mp4") * 1000
    assert base_ms == pytest.approx(5000, abs=800)

    # Final Timeline: scene first, montage second, contiguous.
    timeline = json.loads((job_dir / "final_timeline.json").read_text("utf-8"))
    assert timeline["segments"][0]["kind"] == "scene"
    montage_segs = [s for s in timeline["segments"] if s["kind"] == "montage"]
    assert montage_segs, "expected a montage segment after the scene segment"
    assert montage_segs[0]["start_ms"] == timeline["segments"][0]["end_ms"]
    assert timeline["segments"][0]["start_ms"] == 0


# ---------------------------------------------------------------------------
# 3. video_rendering without a Montage Segment → structured failure
# ---------------------------------------------------------------------------


def test_video_rendering_without_montage_segment_reports_structured_failure_via_http(
    tmp_path: Path,
) -> None:
    """A missing prior Montage Segment yields an explicit structured failure —
    never a silent degrade to an empty base video (AC-4)."""
    root = tmp_path
    client = TestClient(create_app(root))

    resp = client.post(
        f"/api/projects/{PROJECT_ID}/jobs",
        json={"product": "test", "platforms": ["douyin"], "mode": "generate"},
    )
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    # Move the job directly to video_rendering with no montage_segment.mp4.
    data = _load_control_job(root, job_id)
    data["phase"] = "video_rendering"
    data["review_status"] = "none"
    _write_control_job(root, job_id, data)
    job_dir = _runtime_job_dir(root, job_id)
    job_dir.mkdir(parents=True, exist_ok=True)

    svc = _make_tick_service(client, root)
    project_dir = root / "workspace" / "projects" / PROJECT_ID
    # Tick enough times to exhaust retries and reach the terminal failure.
    for _ in range(5):
        current = _load_control_job(root, job_id)
        if current["phase"] == "failed":
            break
        svc.tick(
            PROJECT_ID,
            job_id,
            "test",
            root_dir=root,
            project_dir=project_dir,
        )

    final = _load_control_job(root, job_id)
    assert final["phase"] == "failed"
    assert final["failed_phase"] == "video_rendering"
    assert final["execution"]["status"] == "failed"
    assert final["execution"]["error"]["code"] == "VIDEO_MONTAGE_SEGMENT_MISSING"

    # No silent empty video was produced.
    assert not (job_dir / "base.mp4").exists()
