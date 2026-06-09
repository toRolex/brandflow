import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from apps.control_plane.app import _auto_tick, _phase_to_artifacts


def test_video_rendering_uses_media_bridge_with_selected_clips(monkeypatch, tmp_path: Path) -> None:
    root_dir = tmp_path
    workspace_dir = root_dir / "workspace"
    project_dir = workspace_dir / "projects" / "project-001"
    job_dir = project_dir / "runtime" / "jobs" / "job-001"
    job_dir.mkdir(parents=True, exist_ok=True)

    clip_a = tmp_path / "clip_a.mp4"
    clip_b = tmp_path / "clip_b.mp4"
    clip_a.write_bytes(b"a")
    clip_b.write_bytes(b"b")
    (job_dir / "audio.mp3").write_bytes(b"audio")
    (job_dir / "selected_clips.json").write_text(
        json.dumps(
            [
                {"file_path": str(clip_a)},
                {"file_path": str(clip_b)},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured: dict[str, Any] = {}

    class StubMediaBridge:
        def __init__(self, _root_dir: Path) -> None:
            pass

        def build_base_video(self, actual_project_dir: Path, payload: dict, output_path: Path) -> None:
            captured["project_dir"] = actual_project_dir
            captured["payload"] = payload
            captured["output_path"] = output_path
            output_path.write_bytes(b"video")

    class StubScheduleBridge:
        def __init__(self, _path: Path) -> None:
            pass

    monkeypatch.setattr("apps.control_plane.app.load_environment", lambda _root_dir: None)
    monkeypatch.setattr("apps.control_plane.app.LegacyMediaBridge", StubMediaBridge)
    monkeypatch.setattr("apps.control_plane.app.LegacyScheduleBridge", StubScheduleBridge)

    artifacts = _phase_to_artifacts(
        "video_rendering",
        "job-001",
        project_dir,
        root_dir,
        "荔枝菌",
    )

    assert captured["project_dir"] == project_dir
    assert captured["output_path"] == job_dir / "base.mp4"
    assert captured["payload"]["asset_bundle"]["audio_path"] == str(job_dir / "audio.mp3")
    assert captured["payload"]["asset_bundle"]["selected_clips"] == [
        {"file_path": str(clip_a)},
        {"file_path": str(clip_b)},
    ]
    assert artifacts[0]["kind"] == "video_base"


def test_final_review_allows_missing_srt_when_skip_subtitle_is_enabled(monkeypatch, tmp_path: Path) -> None:
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

    class StubMediaBridge:
        def __init__(self, _root_dir: Path) -> None:
            pass

        def burn_final_video(
            self,
            base_video_path: Path,
            audio_path: Path,
            srt_path: Path | None = None,
            final_video_path: Path | None = None,
            cover_clip_path: Path | None = None,
        ) -> None:
            captured["base_video_path"] = base_video_path
            captured["audio_path"] = audio_path
            captured["srt_path"] = srt_path
            captured["final_video_path"] = final_video_path
            captured["cover_clip_path"] = cover_clip_path
            assert final_video_path is not None
            final_video_path.write_bytes(b"final")

    class StubScheduleBridge:
        def __init__(self, _path: Path) -> None:
            self.calls: list[tuple[str, dict, Path]] = []

        def append(self, project_name: str, payload: dict, final_video_path: Path) -> None:
            self.calls.append((project_name, payload, final_video_path))

    monkeypatch.setattr("apps.control_plane.app.load_environment", lambda _root_dir: None)
    monkeypatch.setattr("apps.control_plane.app.LegacyMediaBridge", StubMediaBridge)
    monkeypatch.setattr("apps.control_plane.app.LegacyScheduleBridge", StubScheduleBridge)

    artifacts = _phase_to_artifacts(
        "final_review",
        "job-001",
        project_dir,
        root_dir,
        "荔枝菌",
    )

    assert captured["srt_path"] is None
    assert artifacts[0]["kind"] == "final_video"


def test_auto_tick_skips_subtitle_phase_when_skip_subtitle_is_enabled(monkeypatch, tmp_path: Path) -> None:
    root_dir = tmp_path
    job_path = root_dir / "workspace" / "projects" / "project-001" / "control" / "jobs" / "job-001.json"
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
        ) + "\n",
        encoding="utf-8",
    )

    sleep_calls = {"count": 0}

    async def fake_sleep(_seconds: float) -> None:
        if sleep_calls["count"] == 0:
            sleep_calls["count"] += 1
            return
        raise asyncio.CancelledError()

    def fail_phase_to_artifacts(*args, **kwargs):
        raise AssertionError("_phase_to_artifacts should not be called when skip_subtitle=True")

    monkeypatch.setattr("apps.control_plane.app.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("apps.control_plane.app._phase_to_artifacts", fail_phase_to_artifacts)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_auto_tick(root_dir))

    data = json.loads(job_path.read_text(encoding="utf-8"))
    assert data["phase"] == "asset_retrieving"
    assert data["review_status"] == "none"


def test_auto_tick_auto_approves_review_gates(monkeypatch, tmp_path: Path) -> None:
    root_dir = tmp_path
    job_path = root_dir / "workspace" / "projects" / "project-001" / "control" / "jobs" / "job-001.json"
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
        ) + "\n",
        encoding="utf-8",
    )

    sleep_calls = {"count": 0}

    async def fake_sleep(_seconds: float) -> None:
        if sleep_calls["count"] == 0:
            sleep_calls["count"] += 1
            return
        raise asyncio.CancelledError()

    def fail_phase_to_artifacts(*args, **kwargs):
        raise AssertionError("_phase_to_artifacts should not be called when auto_approve=True")

    monkeypatch.setattr("apps.control_plane.app.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("apps.control_plane.app._phase_to_artifacts", fail_phase_to_artifacts)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_auto_tick(root_dir))

    data = json.loads(job_path.read_text(encoding="utf-8"))
    assert data["phase"] == "tts_generating"
    assert data["review_status"] == "approved"
