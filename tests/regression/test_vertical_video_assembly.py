from pathlib import Path

from main_controller import PipelineController


def test_legacy_build_base_video_delegates_to_vertical_assembler(monkeypatch, tmp_path: Path) -> None:
    controller = PipelineController(
        root_dir=tmp_path,
        host="127.0.0.1",
        port=0,
        batch_size=1,
        dry_run=False,
    )

    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    source_a = tmp_path / "clip_a.mp4"
    source_b = tmp_path / "clip_b.mp4"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")
    output_path = tmp_path / "base.mp4"
    captured: dict[str, object] = {}

    monkeypatch.setattr(controller, "_get_media_duration", lambda _: 2.0)
    monkeypatch.setattr(controller, "_ffmpeg_path", lambda: Path("ffmpeg"))

    def fake_run_subprocess(cmd: list[str], _label: str):
        Path(cmd[-1]).write_bytes(b"trimmed")

        class Result:
            stdout = ""

        return Result()

    def fake_assemble_vertical_base_video(**kwargs):
        captured.update(kwargs)
        Path(kwargs["output_path"]).write_bytes(b"base")

    monkeypatch.setattr(controller, "_run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(
        "main_controller.assemble_vertical_base_video",
        fake_assemble_vertical_base_video,
        raising=False,
    )

    job = {
        "job_id": "job001",
        "sequence": 1,
        "asset_bundle": {
            "audio_path": str(audio_path),
            "selected_clips": [
                {"file_path": str(source_a), "duration_seconds": 1.0},
                {"file_path": str(source_b), "duration_seconds": 1.0},
            ],
        },
    }

    controller._build_base_video(tmp_path, job, output_path)

    clip_paths = captured["clip_paths"]
    assert isinstance(clip_paths, list)
    assert len(clip_paths) == 2
    assert captured["audio_duration"] == 2.0
    assert captured["output_path"] == output_path
    assert output_path.exists()
