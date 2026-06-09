from pathlib import Path

from main_controller import PipelineController
from packages.pipeline_services.legacy_media_bridge import LegacyMediaBridge


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
    monkeypatch.setattr(controller, "_get_video_size", lambda _: (1080, 1920))
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



def test_legacy_burn_final_video_supports_optional_srt_and_keeps_old_order(monkeypatch, tmp_path: Path) -> None:
    bridge = LegacyMediaBridge(tmp_path)
    captured: list[tuple[Path, Path, Path | None, Path, Path | None]] = []

    def fake_burn_final_video(base_video_path: Path, audio_path: Path, srt_path: Path | None, final_video_path: Path, cover_clip_path: Path | None) -> None:
        captured.append((base_video_path, audio_path, srt_path, final_video_path, cover_clip_path))

    monkeypatch.setattr(bridge.controller, "_burn_final_video", fake_burn_final_video)

    base_video_path = tmp_path / "base.mp4"
    audio_path = tmp_path / "audio.mp3"
    final_video_path = tmp_path / "final.mp4"
    legacy_srt_path = tmp_path / "subtitles.srt"

    bridge.burn_final_video(
        base_video_path=base_video_path,
        audio_path=audio_path,
        final_video_path=final_video_path,
        cover_clip_path=None,
    )
    bridge.burn_final_video(base_video_path, audio_path, legacy_srt_path, final_video_path, cover_clip_path=None)

    assert captured[0] == (base_video_path, audio_path, None, final_video_path, None)
    assert captured[1] == (base_video_path, audio_path, legacy_srt_path, final_video_path, None)



def test_pipeline_controller_burn_final_video_allows_missing_srt_without_subtitles_filter(monkeypatch, tmp_path: Path) -> None:
    controller = PipelineController(
        root_dir=tmp_path,
        host="127.0.0.1",
        port=0,
        batch_size=1,
        dry_run=False,
    )

    base_video_path = tmp_path / "base.mp4"
    audio_path = tmp_path / "audio.mp3"
    final_video_path = tmp_path / "final.mp4"
    cover_clip_path = tmp_path / "cover.mp4"
    base_video_path.write_bytes(b"base")
    audio_path.write_bytes(b"audio")
    cover_clip_path.write_bytes(b"cover")

    captured: list[list[str]] = []

    def fake_run_ffmpeg_with_encoder_fallback(build_cmd, _label: str):
        cmd = build_cmd(["-c:v", "libx264"])
        captured.append(cmd)
        final_video_path.write_bytes(b"final")

    monkeypatch.setattr(controller, "_ffmpeg_path", lambda: Path("ffmpeg"))
    monkeypatch.setattr(controller, "_run_ffmpeg_with_encoder_fallback", fake_run_ffmpeg_with_encoder_fallback)
    monkeypatch.setattr(controller, "_get_video_size", lambda _: (1280, 720))

    controller._burn_final_video(base_video_path, audio_path, None, final_video_path, cover_clip_path=None)
    controller._burn_final_video(base_video_path, audio_path, None, final_video_path, cover_clip_path=cover_clip_path)

    assert all("subtitles=" not in part for cmd in captured for part in cmd)
    assert "-vf" not in captured[0]
    assert any("concat=n=2:v=1:a=0" in part for part in captured[1])
    assert any("[cv]" in part for part in captured[1])
