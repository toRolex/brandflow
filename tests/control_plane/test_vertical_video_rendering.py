import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from apps.control_plane.app import _auto_tick
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
)


def _make_orchestrator(root_dir: Path, video_svc, schedule_store) -> PhaseOrchestrator:
    """Build an orchestrator with stubs for video_svc and schedule_store."""
    from packages.pipeline_services.subtitle_service import SubtitleService

    class StubTTSProvider:
        def synthesize(self, text: str, config: Any) -> bytes:
            return b"tts"

    orch = PhaseOrchestrator(
        subtitle_svc=SubtitleService(),
        video_svc=video_svc,
        schedule_store=schedule_store,
    )
    stub = StubTTSProvider()
    orch._build_tts_provider = lambda cfg: stub
    return orch


def test_video_rendering_composes_prebuilt_montage_segment(
    monkeypatch, tmp_path: Path
) -> None:
    """After #264, _run_video composes the pre-built montage_segment.mp4 into
    base.mp4 instead of calling build_base_video directly."""
    root_dir = tmp_path
    workspace_dir = root_dir / "workspace"
    project_dir = workspace_dir / "projects" / "project-001"
    job_dir = project_dir / "runtime" / "jobs" / "job-001"
    job_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "montage_segment.mp4").write_text("montage video")
    (job_dir / "montage_segments.json").write_text(
        json.dumps(
            [{"sentence": "s", "visual_type": "blank", "duration": 1.0}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class StubVideoService:
        def __init__(self, dry_run: bool = False) -> None:
            pass

    class StubScheduleStore:
        def __init__(self, _root_dir: Path) -> None:
            pass

        def add(
            self, job_id: str, platform: str, title: str = "", description: str = ""
        ) -> int:
            return 1

    video_svc = StubVideoService()
    schedule_store = StubScheduleStore(root_dir)
    orchestrator = _make_orchestrator(root_dir, video_svc, schedule_store)

    ctx = PhaseContext(
        job_id="job-001",
        project_dir=project_dir,
        root_dir=root_dir,
        product="荔枝菌",
    )
    artifacts = orchestrator.run_phase("video_rendering", ctx)

    assert len(artifacts) == 1
    assert artifacts[0].kind == "video_base"
    base_path = job_dir / "base.mp4"
    assert base_path.exists()
    assert base_path.read_text() == "montage video"


def test_final_rendering_allows_missing_srt_when_skip_subtitle_is_enabled(
    monkeypatch, tmp_path: Path
) -> None:
    root_dir = tmp_path
    workspace_dir = root_dir / "workspace"
    project_dir = workspace_dir / "projects" / "project-001"
    job_dir = project_dir / "runtime" / "jobs" / "job-001"
    control_dir = project_dir / "control" / "jobs"
    job_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "base.mp4").write_bytes(b"base")
    (job_dir / "audio.mp3").write_bytes(b"audio")
    (control_dir / "job-001.json").write_text(
        json.dumps({"job_id": "job-001", "skip_subtitle": True}, ensure_ascii=False),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    class StubVideoService:
        def __init__(self, dry_run: bool = False) -> None:
            pass

        def burn_final_video(
            self,
            base_video_path: Path,
            audio_path: Path,
            srt_path: Path | None = None,
            final_video_path: Path | None = None,
            cover_clip_path: Path | None = None,
            cover_title: dict | None = None,
            music_path: Path | None = None,
            music_volume: int = 80,
        ) -> None:
            captured["base_video_path"] = base_video_path
            captured["audio_path"] = audio_path
            captured["srt_path"] = srt_path
            captured["final_video_path"] = final_video_path
            captured["cover_clip_path"] = cover_clip_path
            captured["music_path"] = music_path
            captured["music_volume"] = music_volume
            assert final_video_path is not None
            import subprocess

            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=64x64:d=1",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-an",
                    str(final_video_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

    class StubScheduleStore:
        def __init__(self, _root_dir: Path) -> None:
            self.calls: list[tuple] = []

        def add(
            self, job_id: str, platform: str, title: str = "", description: str = ""
        ) -> int:
            self.calls.append((job_id, platform, title, description))
            return 1

    video_svc = StubVideoService()
    schedule_store = StubScheduleStore(root_dir)
    orchestrator = _make_orchestrator(root_dir, video_svc, schedule_store)

    ctx = PhaseContext(
        job_id="job-001",
        project_dir=project_dir,
        root_dir=root_dir,
        product="荔枝菌",
    )
    artifacts = orchestrator.run_phase("final_rendering", ctx)

    assert captured["srt_path"] is None
    assert artifacts[0].kind == "final_video"


def test_auto_tick_skips_subtitle_phase_when_skip_subtitle_is_enabled(
    monkeypatch, tmp_path: Path
) -> None:
    root_dir = tmp_path
    job_path = (
        root_dir
        / "workspace"
        / "projects"
        / "project-001"
        / "control"
        / "jobs"
        / "job-001.json"
    )
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(
        json.dumps(
            {
                "job_id": "job-001",
                "phase": "subtitle_generating",
                "review_status": "none",
                "skip_subtitle": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    sleep_calls = {"count": 0}

    async def fake_sleep(_seconds: float) -> None:
        if sleep_calls["count"] == 0:
            sleep_calls["count"] += 1
            return
        raise asyncio.CancelledError()

    class _StubTTS:
        def synthesize(self, text, config):
            return b"tts"

    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator._build_tts_provider_fn",
        lambda self, cfg: _StubTTS(),
    )
    monkeypatch.setattr("apps.control_plane.app.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_auto_tick(root_dir, None))

    data = json.loads(job_path.read_text(encoding="utf-8"))
    # subtitle was skipped (skip_subtitle=True) — tick advanced past subtitle
    assert data["phase"] in ("asset_retrieving", "asset_review"), (
        f"expected asset phase after skipping subtitle, got {data['phase']}"
    )
    # review_status may become "pending" if tick reaches asset_review


def test_auto_tick_auto_approves_review_gates(monkeypatch, tmp_path: Path) -> None:
    root_dir = tmp_path
    job_path = (
        root_dir
        / "workspace"
        / "projects"
        / "project-001"
        / "control"
        / "jobs"
        / "job-001.json"
    )
    job_path.parent.mkdir(parents=True, exist_ok=True)
    job_path.write_text(
        json.dumps(
            {
                "job_id": "job-001",
                "phase": "script_review",
                "review_status": "none",
                "auto_approve": True,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    sleep_calls = {"count": 0}

    async def fake_sleep(_seconds: float) -> None:
        if sleep_calls["count"] == 0:
            sleep_calls["count"] += 1
            return
        raise asyncio.CancelledError()

    class _StubTTS:
        def synthesize(self, text, config):
            return b"tts"

    monkeypatch.setattr(
        "packages.pipeline_services.phase_orchestrator._build_tts_provider_fn",
        lambda self, cfg: _StubTTS(),
    )
    monkeypatch.setattr("apps.control_plane.app.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_auto_tick(root_dir, None))

    data = json.loads(job_path.read_text(encoding="utf-8"))
    # auto_approve=True — verify review was approved even if TTS fails afterward
    assert data["review_status"] == "approved"
    # TTS may succeed or fail depending on env; the core assertion is the gate was passed
