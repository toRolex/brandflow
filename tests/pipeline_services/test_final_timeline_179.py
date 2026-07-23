"""Tests for Final Timeline generation and AV offset injection (issue #179).

Pure-function seams for ``packages.pipeline_services.final_timeline`` plus
orchestrator integration seams for ``_run_video`` offset injection and
``_run_final_rendering`` offset-SRT consumption.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from packages.pipeline_services.final_timeline import (
    align_audio,
    build_final_timeline,
    compute_scene_offset_ms,
    shift_srt,
)
from packages.pipeline_services.phase_orchestrator import (
    PhaseContext,
    PhaseOrchestrator,
)


# ---------------------------------------------------------------------------
# shift_srt — shift every SRT timestamp by an offset
# ---------------------------------------------------------------------------


class TestShiftSrt:
    def test_shifts_timestamps_by_offset(self) -> None:
        src = (
            "1\n"
            "00:00:00,000 --> 00:00:01,500\n"
            "第一句。\n"
            "\n"
            "2\n"
            "00:00:01,500 --> 00:00:03,000\n"
            "第二句。\n"
        )
        out = shift_srt(src, 2000)
        assert "00:00:02,000 --> 00:00:03,500" in out
        assert "00:00:03,500 --> 00:00:05,000" in out
        # Text and sequence numbers unchanged
        assert "第一句。" in out
        assert "第二句。" in out

    def test_zero_offset_is_identity(self) -> None:
        src = "1\n00:00:01,000 --> 00:00:02,000\n你好。\n"
        assert shift_srt(src, 0) == src

    def test_carries_into_minutes_and_hours(self) -> None:
        src = "1\n00:00:59,500 --> 00:00:59,900\n尾句。\n"
        out = shift_srt(src, 1000)
        assert "00:01:00,500 --> 00:01:00,900" in out

    def test_hour_rollover(self) -> None:
        src = "1\n00:59:59,999 --> 01:00:00,000\n跨时。\n"
        out = shift_srt(src, 1)
        assert "01:00:00,000 --> 01:00:00,001" in out

    def test_empty_input_returns_empty(self) -> None:
        assert shift_srt("", 5000) == ""

    def test_preserves_non_timestamp_lines(self) -> None:
        src = "1\n00:00:00,000 --> 00:00:01,000\n带 --> 符号的文本不偏移\n"
        out = shift_srt(src, 500)
        assert "00:00:00,500 --> 00:00:01,500" in out


# ---------------------------------------------------------------------------
# compute_scene_offset_ms — probe scene segment duration, 0 when absent
# ---------------------------------------------------------------------------


class TestComputeSceneOffsetMs:
    def test_no_scene_returns_zero(self, tmp_path: Path) -> None:
        assert compute_scene_offset_ms(tmp_path / "scene_segment.mp4") == 0

    def test_none_returns_zero(self) -> None:
        assert compute_scene_offset_ms(None) == 0

    def test_existing_scene_probes_duration(self, tmp_path: Path) -> None:
        scene = tmp_path / "scene_segment.mp4"
        scene.write_bytes(b"fake")
        with patch(
            "packages.pipeline_services.final_timeline.get_media_duration",
            return_value=2.345,
        ):
            assert compute_scene_offset_ms(scene) == 2345


# ---------------------------------------------------------------------------
# build_final_timeline — authoritative timeline from render inputs
# ---------------------------------------------------------------------------


def _montage_segments() -> list[dict]:
    """trim_params-style montage segment dicts (already trimmed)."""
    return [
        {
            "sentence": "第一句。",
            "file_path": "/assets/a.mp4",
            "asset_id": "a1",
            "visual_type": "clip",
            "ss": 0.0,
            "duration": 2.0,
        },
        {
            "sentence": "空白句。",
            "file_path": "",
            "asset_id": "",
            "visual_type": "blank",
            "ss": 0.0,
            "duration": 1.5,
        },
        {
            "sentence": "第三句。",
            "file_path": "/assets/b.mp4",
            "asset_id": "b2",
            "visual_type": "clip",
            "ss": 0.5,
            "duration": 2.5,
        },
    ]


class TestBuildFinalTimelineNoScene:
    """No-scene (generate) path: montage starts at 0, offset is identity."""

    def test_segments_contiguous_and_start_at_zero(self) -> None:
        tl = build_final_timeline(scene_ms=0, montage_segments=_montage_segments())
        segs = tl["segments"]
        assert segs[0]["start_ms"] == 0
        for prev, cur in zip(segs, segs[1:]):
            assert cur["start_ms"] == prev["end_ms"], "segments must not overlap"

    def test_no_scene_segment_emitted(self) -> None:
        tl = build_final_timeline(scene_ms=0, montage_segments=_montage_segments())
        assert all(s["kind"] != "scene" for s in tl["segments"])

    def test_kinds_and_sources(self) -> None:
        tl = build_final_timeline(scene_ms=0, montage_segments=_montage_segments())
        segs = tl["segments"]
        assert [s["kind"] for s in segs] == ["montage", "blank", "montage"]
        # source traceability
        assert segs[0]["source"]["asset_id"] == "a1"
        assert segs[0]["source"]["file_path"] == "/assets/a.mp4"
        assert segs[1]["kind"] == "blank"
        assert segs[1]["source"] == {} or segs[1]["source"].get("asset_id", "") == ""

    def test_sentence_traceability(self) -> None:
        tl = build_final_timeline(scene_ms=0, montage_segments=_montage_segments())
        segs = tl["segments"]
        assert segs[0]["sentence_index"] == 0
        assert segs[0]["text"] == "第一句。"
        assert segs[2]["sentence_index"] == 2
        assert segs[2]["text"] == "第三句。"

    def test_total_duration_matches_segments(self) -> None:
        tl = build_final_timeline(scene_ms=0, montage_segments=_montage_segments())
        # 2.0 + 1.5 + 2.5 = 6.0s
        assert tl["segments"][-1]["end_ms"] == 6000
        assert tl["duration_ms"] == 6000


class TestBuildFinalTimelineWithScene:
    """Scene path: scene segment first, montage offset by scene_ms."""

    def test_scene_segment_first_from_zero(self) -> None:
        tl = build_final_timeline(
            scene_ms=2000,
            montage_segments=_montage_segments(),
            scene_source={"files": ["/scene/x.mp4"]},
        )
        segs = tl["segments"]
        assert segs[0]["kind"] == "scene"
        assert segs[0]["start_ms"] == 0
        assert segs[0]["end_ms"] == 2000

    def test_montage_offset_to_scene_end(self) -> None:
        tl = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        segs = tl["segments"]
        montage = [s for s in segs if s["kind"] in ("montage", "blank")]
        assert montage[0]["start_ms"] == 2000

    def test_all_segments_contiguous(self) -> None:
        tl = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        segs = tl["segments"]
        for prev, cur in zip(segs, segs[1:]):
            assert cur["start_ms"] == prev["end_ms"]

    def test_total_includes_scene(self) -> None:
        tl = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        assert tl["duration_ms"] == 2000 + 6000


class TestFinalTimelineFingerprint:
    """Stable fingerprint: content-sensitive, path-insensitive."""

    def test_same_inputs_same_fingerprint(self) -> None:
        a = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        b = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        assert a["fingerprint"] == b["fingerprint"]
        assert a["fingerprint"]

    def test_content_change_changes_fingerprint(self) -> None:
        a = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        changed = _montage_segments()
        changed[1]["duration"] = 9.9  # blank duration change
        b = build_final_timeline(scene_ms=2000, montage_segments=changed)
        assert a["fingerprint"] != b["fingerprint"]

    def test_scene_change_changes_fingerprint(self) -> None:
        a = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        b = build_final_timeline(scene_ms=3000, montage_segments=_montage_segments())
        assert a["fingerprint"] != b["fingerprint"]

    def test_fingerprint_ignores_absolute_path(self) -> None:
        """Fingerprint must be stable across machines: hash content, not abs paths."""
        segs_a = _montage_segments()
        segs_b = _montage_segments()
        segs_b[0]["file_path"] = "/different/machine/a.mp4"  # same basename
        a = build_final_timeline(scene_ms=0, montage_segments=segs_a)
        b = build_final_timeline(scene_ms=0, montage_segments=segs_b)
        assert a["fingerprint"] == b["fingerprint"]


class TestFinalTimelineAlignedFlag:
    def test_aligned_true_by_default(self) -> None:
        tl = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        assert tl["aligned"] is True

    def test_aligned_false_marks_fallback(self) -> None:
        tl = build_final_timeline(
            scene_ms=2000, montage_segments=_montage_segments(), aligned=False
        )
        assert tl["aligned"] is False

    def test_aligned_flag_not_in_fingerprint(self) -> None:
        """aligned reflects render success, not content — excluded from fingerprint."""
        a = build_final_timeline(scene_ms=2000, montage_segments=_montage_segments())
        b = build_final_timeline(
            scene_ms=2000, montage_segments=_montage_segments(), aligned=False
        )
        assert a["fingerprint"] == b["fingerprint"]


# ---------------------------------------------------------------------------
# align_audio — offset TTS audio to the montage start via adelay + apad
# ---------------------------------------------------------------------------


class TestAlignAudio:
    def test_zero_offset_copies_through(self, tmp_path: Path) -> None:
        """No scene → offset 0 → aligned audio is a straight copy (no ffmpeg)."""
        src = tmp_path / "audio.mp3"
        src.write_bytes(b"fake audio")
        out = tmp_path / "audio_aligned.mp3"
        with patch(
            "packages.pipeline_services.final_timeline.subprocess.run"
        ) as mock_run:
            align_audio(src, out, offset_ms=0, total_ms=6000)
        mock_run.assert_not_called()
        assert out.read_bytes() == b"fake audio"

    def test_positive_offset_invokes_adelay_apad(self, tmp_path: Path) -> None:
        """Scene present → adelay=offset then apad, trimmed to total_ms."""
        src = tmp_path / "audio.mp3"
        src.write_bytes(b"fake audio")
        out = tmp_path / "audio_aligned.mp3"

        def _effect(cmd, *a, **k):
            out.write_bytes(b"aligned")
            return MagicMock(returncode=0)

        with (
            patch(
                "packages.pipeline_services.final_timeline.get_ffmpeg_path",
                return_value="ffmpeg",
            ),
            patch(
                "packages.pipeline_services.final_timeline.subprocess.run",
                side_effect=_effect,
            ) as mock_run,
        ):
            align_audio(src, out, offset_ms=2000, total_ms=8000)

        cmd = mock_run.call_args[0][0]
        joined = " ".join(str(c) for c in cmd)
        assert "adelay=2000" in joined
        assert "apad" in joined
        # trimmed to total_ms = 8s
        assert "-t" in cmd
        t_idx = cmd.index("-t")
        assert cmd[t_idx + 1] == "8.000"


# ---------------------------------------------------------------------------
# _run_video AV-alignment injection (orchestrator integration)
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture()
def project_dir(tmp_root: Path) -> Path:
    d = tmp_root / "workspace" / "projects" / "proj-001"
    d.mkdir(parents=True)
    return d


@pytest.fixture()
def ctx(project_dir: Path, tmp_root: Path) -> PhaseContext:
    return PhaseContext(
        job_id="job-001",
        project_dir=project_dir,
        root_dir=tmp_root,
        product="test",
        options={},
    )


@pytest.fixture()
def orchestrator() -> PhaseOrchestrator:
    return PhaseOrchestrator(
        subtitle_svc=MagicMock(),
        video_svc=MagicMock(),
        schedule_store=MagicMock(),
    )


class TestRunVideoAlignmentInjection:
    """_run_video must emit audio_aligned.mp3, subtitles_offset.srt and
    final_timeline.json alongside base.mp4 (issue #179).

    After #264 montage_assembling produces montage_segment.mp4 +
    montage_segments.json; video_rendering consumes these instead of
    calling build_base_video directly."""

    def _setup_job(self, ctx: PhaseContext, *, with_scene: bool) -> Path:
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "montage_segment.mp4").write_bytes(b"pre-built montage segment")
        (job_dir / "montage_segments.json").write_text(
            json.dumps(
                [
                    {
                        "sentence": "第一句。",
                        "file_path": str(job_dir / "clip1.mp4"),
                        "asset_id": "a1",
                        "duration_seconds": 5.0,
                        "visual_type": "clip",
                        "ss": 0.0,
                        "duration": 1.5,
                    },
                    {
                        "sentence": "空白句。",
                        "file_path": "",
                        "asset_id": "",
                        "duration_seconds": 0.0,
                        "visual_type": "blank",
                        "ss": 0.0,
                        "duration": 1.5,
                    },
                ]
            ),
            encoding="utf-8",
        )
        if with_scene:
            (job_dir / "scene_segment.mp4").write_bytes(b"fake scene video")
        (job_dir / "audio.mp3").write_bytes(b"fake audio")
        (job_dir / "subtitles.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n第一句。\n", encoding="utf-8"
        )
        return job_dir

    def test_emits_aligned_audio_and_offset_srt_and_timeline_with_scene(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        job_dir = self._setup_job(ctx, with_scene=True)

        def _ffmpeg_effect(cmd, *a, **k):
            # concat produces base.mp4; align produces audio_aligned.mp3
            joined = " ".join(str(c) for c in cmd)
            if "concat" in joined:
                (job_dir / "base.mp4").write_bytes(b"base video")
            if "adelay" in joined:
                (job_dir / "audio_aligned.mp3").write_bytes(b"aligned audio")
            return MagicMock(returncode=0)

        with (
            patch.object(orchestrator, "_get_ffmpeg_path", return_value="ffmpeg"),
            patch.object(orchestrator, "_get_media_duration", return_value=3.0),
            patch(
                "packages.pipeline_services.phase_orchestrator.subprocess.run",
                side_effect=_ffmpeg_effect,
            ),
            patch(
                "packages.pipeline_services.final_timeline.get_media_duration",
                return_value=3.0,
            ),
            patch(
                "packages.pipeline_services.final_timeline.get_ffmpeg_path",
                return_value="ffmpeg",
            ),
            patch(
                "packages.pipeline_services.final_timeline.subprocess.run",
                side_effect=_ffmpeg_effect,
            ),
        ):
            artifacts = orchestrator.run_phase("video_rendering", ctx)

        # base.mp4 produced
        assert (job_dir / "base.mp4").exists()
        # aligned audio + offset srt + timeline emitted
        assert (job_dir / "audio_aligned.mp3").exists()
        offset_srt = job_dir / "subtitles_offset.srt"
        assert offset_srt.exists()
        # offset srt shifted by scene_ms (3.0s): 00:00:00,000 -> 00:00:03,000
        assert "00:00:03,000 --> 00:00:05,000" in offset_srt.read_text(encoding="utf-8")
        # final timeline persisted
        timeline_path = job_dir / "final_timeline.json"
        assert timeline_path.exists()
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        assert timeline["aligned"] is True
        assert timeline["fingerprint"]
        kinds = [s["kind"] for s in timeline["segments"]]
        assert kinds[0] == "scene"
        assert "montage" in kinds and "blank" in kinds
        assert any(a.kind == "video_base" for a in artifacts)

    def test_no_scene_uses_zero_offset_same_code_path(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        job_dir = self._setup_job(ctx, with_scene=False)

        with (
            patch.object(orchestrator, "_get_ffmpeg_path", return_value="ffmpeg"),
            patch.object(orchestrator, "_get_media_duration", return_value=3.0),
            patch(
                "packages.pipeline_services.final_timeline.get_media_duration",
                return_value=3.0,
            ),
        ):
            orchestrator.run_phase("video_rendering", ctx)

        timeline = json.loads(
            (job_dir / "final_timeline.json").read_text(encoding="utf-8")
        )
        # no scene segment emitted; montage starts at 0
        assert all(s["kind"] != "scene" for s in timeline["segments"])
        assert timeline["segments"][0]["start_ms"] == 0
        # offset srt is identity (offset 0)
        offset_srt = (job_dir / "subtitles_offset.srt").read_text(encoding="utf-8")
        assert "00:00:00,000 --> 00:00:02,000" in offset_srt

    def test_align_failure_falls_back_and_marks_unaligned(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        job_dir = self._setup_job(ctx, with_scene=True)

        def _ffmpeg_effect(cmd, *a, **k):
            joined = " ".join(str(c) for c in cmd)
            if "concat" in joined:
                (job_dir / "base.mp4").write_bytes(b"base video")
            if "adelay" in joined:
                raise subprocess.CalledProcessError(1, cmd, stderr="boom")
            return MagicMock(returncode=0)

        with (
            patch.object(orchestrator, "_get_ffmpeg_path", return_value="ffmpeg"),
            patch.object(orchestrator, "_get_media_duration", return_value=3.0),
            patch(
                "packages.pipeline_services.phase_orchestrator.subprocess.run",
                side_effect=_ffmpeg_effect,
            ),
            patch(
                "packages.pipeline_services.final_timeline.get_media_duration",
                return_value=3.0,
            ),
            patch(
                "packages.pipeline_services.final_timeline.get_ffmpeg_path",
                return_value="ffmpeg",
            ),
            patch(
                "packages.pipeline_services.final_timeline.subprocess.run",
                side_effect=_ffmpeg_effect,
            ),
        ):
            orchestrator.run_phase("video_rendering", ctx)

        # base still produced; timeline marks aligned: false
        assert (job_dir / "base.mp4").exists()
        timeline = json.loads(
            (job_dir / "final_timeline.json").read_text(encoding="utf-8")
        )
        assert timeline["aligned"] is False


# ---------------------------------------------------------------------------
# _run_final_rendering consumes aligned audio + offset srt
# ---------------------------------------------------------------------------


class TestRunFinalRenderingAlignment:
    """final_rendering must prefer audio_aligned.mp3 + subtitles_offset.srt."""

    def _setup(self, ctx: PhaseContext, *, aligned: bool) -> Path:
        job_dir = ctx.project_dir / "runtime" / "jobs" / ctx.job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "base.mp4").write_bytes(b"base video")
        (job_dir / "audio.mp3").write_bytes(b"original audio")
        (job_dir / "subtitles.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\n第一句。\n", encoding="utf-8"
        )
        if aligned:
            (job_dir / "audio_aligned.mp3").write_bytes(b"aligned audio")
            (job_dir / "subtitles_offset.srt").write_text(
                "1\n00:00:03,000 --> 00:00:05,000\n第一句。\n", encoding="utf-8"
            )
        return job_dir

    def _burn_spy(self, orchestrator: PhaseOrchestrator, job_dir: Path) -> MagicMock:
        def _burn(base, audio, srt, final, **kwargs):
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
                    str(final),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

        orchestrator._video_svc.burn_final_video.side_effect = _burn
        return orchestrator._video_svc.burn_final_video

    def test_prefers_aligned_audio_and_offset_srt(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        job_dir = self._setup(ctx, aligned=True)
        burn = self._burn_spy(orchestrator, job_dir)

        artifacts = orchestrator.run_phase("final_rendering", ctx)

        burn.assert_called_once()
        audio_arg = burn.call_args[0][1]
        srt_arg = burn.call_args[0][2]
        assert Path(audio_arg).name == "audio_aligned.mp3"
        assert Path(srt_arg).name == "subtitles_offset.srt"
        assert any(a.kind == "final_video" for a in artifacts)

    def test_falls_back_to_originals_when_not_aligned(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        job_dir = self._setup(ctx, aligned=False)
        burn = self._burn_spy(orchestrator, job_dir)

        orchestrator.run_phase("final_rendering", ctx)

        audio_arg = burn.call_args[0][1]
        srt_arg = burn.call_args[0][2]
        assert Path(audio_arg).name == "audio.mp3"
        assert Path(srt_arg).name == "subtitles.srt"

    def test_skip_subtitle_passes_none_even_with_offset_srt(
        self, orchestrator: PhaseOrchestrator, ctx: PhaseContext
    ) -> None:
        job_dir = self._setup(ctx, aligned=True)
        # job JSON marks skip_subtitle
        job_json_dir = ctx.project_dir / "control" / "jobs"
        job_json_dir.mkdir(parents=True, exist_ok=True)
        (job_json_dir / f"{ctx.job_id}.json").write_text(
            json.dumps({"skip_subtitle": True}), encoding="utf-8"
        )
        burn = self._burn_spy(orchestrator, job_dir)

        orchestrator.run_phase("final_rendering", ctx)

        assert burn.call_args[0][2] is None
        # audio still prefers aligned
        assert Path(burn.call_args[0][1]).name == "audio_aligned.mp3"


# ---------------------------------------------------------------------------
# build_export_bundle prefers the authoritative Final Timeline (no dir scan)
# ---------------------------------------------------------------------------


class TestExportBundleFinalTimeline:
    """Export must embed the render-time Final Timeline, not a re-derived one."""

    def _write_final_timeline(self, job_dir: Path) -> dict:
        timeline = {
            "version": "1.0",
            "duration_ms": 5000,
            "aligned": True,
            "fingerprint": "deadbeefcafe",
            "segments": [
                {
                    "kind": "scene",
                    "start_ms": 0,
                    "end_ms": 2000,
                    "sentence_index": None,
                    "text": "",
                    "source": {},
                },
                {
                    "kind": "montage",
                    "start_ms": 2000,
                    "end_ms": 5000,
                    "sentence_index": 0,
                    "text": "第一句。",
                    "source": {"asset_id": "a1"},
                },
            ],
        }
        (job_dir / "final_timeline.json").write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return timeline

    def test_export_uses_authoritative_final_timeline(self, tmp_path: Path) -> None:
        import zipfile

        from packages.pipeline_services.export_service import build_export_bundle

        workspace_dir = tmp_path / "workspace"
        project_dir = workspace_dir / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        job_dir.mkdir(parents=True, exist_ok=True)
        export_dir = project_dir / "runtime" / "exports"
        # Empty segments → segment_final_video is a no-op (no real FFmpeg needed);
        # the fingerprint still flows from the authoritative render-time timeline.
        self._write_final_timeline(job_dir)

        zip_path = build_export_bundle(
            job_dir,
            workspace_dir,
            project_dir,
            export_dir,
            get_scene_config=lambda: {"folders": [], "transition_duration_ms": 500},
        )

        with zipfile.ZipFile(zip_path, "r") as zf:
            embedded = json.loads(zf.read("export_job-001/timeline.json"))

        # Since #181 the embedded timeline is the flat 2.0 projection, but it is
        # still derived from the authoritative render-time one (fingerprint intact).
        assert embedded["version"] == "2.0"
        assert embedded["fingerprint"] == "deadbeefcafe"

    def test_export_falls_back_to_legacy_when_no_final_timeline(
        self, tmp_path: Path
    ) -> None:
        import pytest

        from packages.pipeline_services.export_service import (
            RerenderRequiredError,
            build_export_bundle,
        )

        workspace_dir = tmp_path / "workspace"
        project_dir = workspace_dir / "projects" / "proj-001"
        job_dir = project_dir / "runtime" / "jobs" / "job-001"
        job_dir.mkdir(parents=True, exist_ok=True)
        export_dir = project_dir / "runtime" / "exports"
        (job_dir / "final.mp4").write_bytes(b"final video")
        # no final_timeline.json → export now requires a re-render (#181)

        with pytest.raises(RerenderRequiredError):
            build_export_bundle(
                job_dir,
                workspace_dir,
                project_dir,
                export_dir,
                get_scene_config=lambda: {"folders": [], "transition_duration_ms": 500},
            )
