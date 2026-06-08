import json
from pathlib import Path

from apps.control_plane.app import _phase_to_artifacts


def test_video_rendering_uses_shared_vertical_assembler(monkeypatch, tmp_path: Path) -> None:
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

    captured: dict[str, object] = {}

    def fake_duration(path: Path) -> float:
        assert path == job_dir / "audio.mp3"
        return 3.2

    def fake_assemble_vertical_base_video(**kwargs):
        captured.update(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"video")

    monkeypatch.setattr("apps.control_plane.app.get_media_duration", fake_duration)
    monkeypatch.setattr(
        "apps.control_plane.app.assemble_vertical_base_video",
        fake_assemble_vertical_base_video,
        raising=False,
    )

    artifacts = _phase_to_artifacts(
        "video_rendering",
        "job-001",
        project_dir,
        root_dir,
        "荔枝菌",
    )

    assert captured["clip_paths"] == [clip_a, clip_b]
    assert captured["audio_duration"] == 3.2
    assert "crop=iw*" not in str(captured["recipe_filter"])
    assert "scale=iw:ih" not in str(captured["recipe_filter"])
    assert artifacts[0]["kind"] == "video_base"
