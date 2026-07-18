"""Tests for precise MP4 segmentation + timeline.json 2.0 (issue #181).

Covers:
- build_timeline_2: pure-function Final Timeline -> flat playback-order schema 2.0
- segment_final_video: real-FFmpeg exact-boundary split of final.mp4
- build_export_bundle integration: final/ holds final.mp4 + seg_NNN.mp4, 2.0 timeline
- legacy (no Final Timeline) jobs fail with an explicit re-render error
"""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from packages.pipeline_services.media_utils import (
    get_ffmpeg_path,
    get_ffprobe_path,
    get_media_duration,
)
from packages.pipeline_services.segment_export import (
    build_timeline_2,
    segment_final_video,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _final_timeline() -> dict:
    """Render-time Final Timeline (issue #179 shape): scene + montage + blank."""
    return {
        "version": "1.0",
        "duration_ms": 6000,
        "aligned": True,
        "fingerprint": "deadbeefcafe",
        "segments": [
            {
                "kind": "scene",
                "start_ms": 0,
                "end_ms": 2000,
                "sentence_index": None,
                "text": "",
                "source": {"file_path": "/assets/scene.mp4"},
            },
            {
                "kind": "montage",
                "start_ms": 2000,
                "end_ms": 4000,
                "sentence_index": 0,
                "text": "第一句。",
                "source": {"asset_id": "a1", "file_path": "/assets/a.mp4"},
            },
            {
                "kind": "blank",
                "start_ms": 4000,
                "end_ms": 5000,
                "sentence_index": 1,
                "text": "空白句。",
                "source": {},
            },
            {
                "kind": "montage",
                "start_ms": 5000,
                "end_ms": 6000,
                "sentence_index": 2,
                "text": "第三句。",
                "source": {"asset_id": "b2", "file_path": "/assets/b.mp4"},
            },
        ],
    }


def _make_av_mp4(path: Path, duration_s: float = 6.0) -> None:
    """Create a real MP4 with video + audio streams via ffmpeg testsrc2 + sine."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            get_ffmpeg_path(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size=320x240:rate=24:duration={duration_s}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_s}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _has_audio_stream(path: Path) -> bool:
    result = subprocess.run(
        [
            get_ffprobe_path(),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return "audio" in result.stdout


# ---------------------------------------------------------------------------
# build_timeline_2 — pure-function schema 2.0 conversion
# ---------------------------------------------------------------------------


class TestBuildTimeline2:
    def test_flat_playback_order_with_rendered_files(self) -> None:
        tl2 = build_timeline_2(_final_timeline())
        assert tl2["version"] == "2.0"
        segs = tl2["segments"]
        # flat playback order, one rendered_file per segment
        assert [s["rendered_file"] for s in segs] == [
            "final/seg_001.mp4",
            "final/seg_002.mp4",
            "final/seg_003.mp4",
            "final/seg_004.mp4",
        ]

    def test_segment_count_equals_timeline_segments(self) -> None:
        tl = _final_timeline()
        tl2 = build_timeline_2(tl)
        assert len(tl2["segments"]) == len(tl["segments"])

    def test_schema_fields_carried(self) -> None:
        tl2 = build_timeline_2(_final_timeline())
        assert tl2["duration_ms"] == 6000
        assert tl2["fingerprint"] == "deadbeefcafe"
        s = tl2["segments"][1]
        assert s["kind"] == "montage"
        assert s["start_ms"] == 2000
        assert s["end_ms"] == 4000
        assert s["sentence_index"] == 0
        assert s["text"] == "第一句。"

    def test_source_file_optional(self) -> None:
        tl2 = build_timeline_2(_final_timeline())
        segs = tl2["segments"]
        # montage segments carry the original asset basename as source_file
        assert segs[1]["source_file"] == "a.mp4"
        assert segs[3]["source_file"] == "b.mp4"
        # blank and scene segments have no montage source asset
        assert "source_file" not in segs[2]

    def test_contiguous_playback_order(self) -> None:
        tl2 = build_timeline_2(_final_timeline())
        segs = tl2["segments"]
        for prev, cur in zip(segs, segs[1:]):
            assert cur["start_ms"] == prev["end_ms"]


# ---------------------------------------------------------------------------
# segment_final_video — real-FFmpeg exact-boundary split
# ---------------------------------------------------------------------------


class TestSegmentFinalVideo:
    def test_produces_playable_segments_with_streams(self, tmp_path: Path) -> None:
        final = tmp_path / "final.mp4"
        _make_av_mp4(final, 6.0)
        out_dir = tmp_path / "segs"

        produced = segment_final_video(final, _final_timeline()["segments"], out_dir)

        assert len(produced) == 4
        for p in produced:
            assert p.exists()
            # independently playable: ffprobe opens it and finds video + audio
            assert get_media_duration(p) > 0
            assert _has_audio_stream(p)

    def test_segment_count_and_continuous_numbering(self, tmp_path: Path) -> None:
        final = tmp_path / "final.mp4"
        _make_av_mp4(final, 6.0)
        produced = segment_final_video(
            final, _final_timeline()["segments"], tmp_path / "s"
        )
        assert [p.name for p in produced] == [
            "seg_001.mp4",
            "seg_002.mp4",
            "seg_003.mp4",
            "seg_004.mp4",
        ]

    def test_segment_durations_match_timeline(self, tmp_path: Path) -> None:
        final = tmp_path / "final.mp4"
        _make_av_mp4(final, 6.0)
        segs = _final_timeline()["segments"]
        produced = segment_final_video(final, segs, tmp_path / "s")

        # expected durations in seconds: 2.0, 2.0, 1.0, 1.0
        expected = [(s["end_ms"] - s["start_ms"]) / 1000.0 for s in segs]
        for path, exp in zip(produced, expected):
            actual = get_media_duration(path)
            assert abs(actual - exp) < 0.25, f"{path.name}: {actual} != {exp}"

    def test_sequential_concat_preserves_total_duration(self, tmp_path: Path) -> None:
        final = tmp_path / "final.mp4"
        _make_av_mp4(final, 6.0)
        total = get_media_duration(final)
        produced = segment_final_video(
            final, _final_timeline()["segments"], tmp_path / "s"
        )
        seg_sum = sum(get_media_duration(p) for p in produced)
        assert abs(seg_sum - total) < 0.5

    def test_reencode_not_stream_copy(self, tmp_path: Path) -> None:
        """Exact boundaries require re-encode, not -c copy."""
        final = tmp_path / "final.mp4"
        _make_av_mp4(final, 6.0)
        calls: list[list[str]] = []

        real_run = subprocess.run

        def _spy(cmd, *a, **k):
            calls.append(cmd)
            return real_run(cmd, *a, **k)

        import packages.pipeline_services.segment_export as mod

        orig = mod.subprocess.run
        mod.subprocess.run = _spy
        try:
            segment_final_video(final, _final_timeline()["segments"], tmp_path / "s")
        finally:
            mod.subprocess.run = orig

        seg_calls = [c for c in calls if "seg_" in str(c)]
        assert seg_calls
        joined = " ".join(str(x) for x in seg_calls[0])
        assert "-c copy" not in joined and "-c:v copy" not in joined


# ---------------------------------------------------------------------------
# build_export_bundle integration — final/ holds final.mp4 + seg_NNN.mp4
# ---------------------------------------------------------------------------


def _setup_job(job_dir: Path, *, with_timeline: bool = True) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    _make_av_mp4(job_dir / "final.mp4", 6.0)
    (job_dir / "audio.mp3").write_bytes(b"audio")
    if with_timeline:
        (job_dir / "final_timeline.json").write_text(
            json.dumps(_final_timeline(), ensure_ascii=False), encoding="utf-8"
        )


class TestExportBundleSegments:
    def _dirs(self, tmp_path: Path) -> tuple[Path, Path, Path, Path]:
        workspace_dir = tmp_path / "workspace"
        project_dir = workspace_dir / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        export_dir = project_dir / "runtime" / "exports"
        job_dir.mkdir(parents=True, exist_ok=True)
        return workspace_dir, project_dir, job_dir, export_dir

    def test_final_dir_has_final_and_segments(self, tmp_path: Path) -> None:
        from packages.pipeline_services.export_service import build_export_bundle

        ws, proj, job_dir, export_dir = self._dirs(tmp_path)
        _setup_job(job_dir)

        zip_path = build_export_bundle(
            job_dir,
            ws,
            proj,
            export_dir,
            get_scene_config=lambda: {"folders": [], "transition_duration_ms": 500},
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        prefix = "export_job-001/"
        assert f"{prefix}final/final.mp4" in names
        assert f"{prefix}final/seg_001.mp4" in names
        assert f"{prefix}final/seg_004.mp4" in names

    def test_embedded_timeline_is_2_0(self, tmp_path: Path) -> None:
        from packages.pipeline_services.export_service import build_export_bundle

        ws, proj, job_dir, export_dir = self._dirs(tmp_path)
        _setup_job(job_dir)

        zip_path = build_export_bundle(
            job_dir,
            ws,
            proj,
            export_dir,
            get_scene_config=lambda: {"folders": [], "transition_duration_ms": 500},
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            tl = json.loads(zf.read("export_job-001/timeline.json"))
        assert tl["version"] == "2.0"
        assert tl["segments"][0]["rendered_file"] == "final/seg_001.mp4"

    def test_no_final_timeline_raises_rerender_error(self, tmp_path: Path) -> None:
        from packages.pipeline_services.export_service import build_export_bundle

        ws, proj, job_dir, export_dir = self._dirs(tmp_path)
        _setup_job(job_dir, with_timeline=False)

        with pytest.raises(Exception, match="[Rr]e-?render|Final Timeline"):
            build_export_bundle(
                job_dir,
                ws,
                proj,
                export_dir,
                get_scene_config=lambda: {"folders": [], "transition_duration_ms": 500},
            )


# ---------------------------------------------------------------------------
# Atomic failure — a segmentation failure never publishes a partial ZIP (#180)
# ---------------------------------------------------------------------------


class TestAtomicSegmentFailure:
    def test_segment_failure_marks_failed_and_no_partial_zip(
        self, tmp_path: Path
    ) -> None:
        from packages.pipeline_services.export_task import ExportTaskService

        workspace_dir = tmp_path / "workspace"
        project_dir = workspace_dir / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        export_dir = project_dir / "runtime" / "exports"
        job_dir.mkdir(parents=True, exist_ok=True)
        # Non-empty segments but a corrupt final.mp4 → ffmpeg segmentation fails.
        (job_dir / "final.mp4").write_bytes(b"not a real mp4")
        (job_dir / "final_timeline.json").write_text(
            json.dumps(_final_timeline(), ensure_ascii=False), encoding="utf-8"
        )

        service = ExportTaskService(
            job_id=job_dir.name,
            job_dir=job_dir,
            workspace_dir=workspace_dir,
            project_dir=project_dir,
            export_dir=export_dir,
            get_scene_config=lambda: {"folders": [], "transition_duration_ms": 500},
        )
        task = service.create_or_reuse(fingerprint="fp-x")
        result = service.run(task["task_id"])

        assert result["status"] == "failed"
        assert result["error"]
        # atomic publish: no partial/corrupt ZIP left downloadable
        assert not Path(result["zip_path"]).exists()


class TestSegmentFfmpegTimeout:
    """segment_final_video calls subprocess.run with timeout=300."""

    def test_segment_ffmpeg_has_timeout(self, tmp_path: Path) -> None:
        from packages.pipeline_services.segment_export import segment_final_video
        import packages.pipeline_services.segment_export as segmod

        final = tmp_path / "final.mp4"
        _make_av_mp4(final, 2.0)
        calls: list = []
        orig_run = segmod.subprocess.run

        def _spy(*args: object, **kwargs: object) -> object:
            calls.append((args[0], kwargs))
            return orig_run(*args, **kwargs)

        segmod.subprocess.run = _spy
        try:
            segment_final_video(
                final, [{"start_ms": 0, "end_ms": 1000}], tmp_path / "s"
            )
        finally:
            segmod.subprocess.run = orig_run

        assert calls, "subprocess.run should have been called"
        for _, kwargs in calls:
            assert kwargs.get("timeout") == 300, (
                f"subprocess.run should have timeout=300, got: {kwargs.get('timeout')}"
            )
