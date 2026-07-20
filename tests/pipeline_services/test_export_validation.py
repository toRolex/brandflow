"""Tests for export ZIP content validation (#255).

Validates that the export ZIP's internal structure is correct before marking the
task ready: final video present, timeline valid, segment count matches,
all segments non-empty, sequential numbering.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from packages.pipeline_services.export_validation import validate_export_zip


def _media_probe(
    *,
    final_duration: float = 3.0,
    segment_durations: dict[str, float] | None = None,
    unplayable: set[str] | None = None,
    audio_codec: str = "mp3",
):
    segment_durations = segment_durations or {}
    unplayable = unplayable or set()

    def probe(path: Path) -> dict[str, object]:
        if path.name in unplayable:
            return {"duration": None, "video_codec": None, "audio_codec": None}
        if path.suffix in {".mp3", ".wav"}:
            return {
                "duration": final_duration,
                "video_codec": None,
                "audio_codec": audio_codec,
            }
        duration = (
            final_duration
            if path.name == "final.mp4"
            else segment_durations.get(path.name, 3.0)
        )
        return {"duration": duration, "video_codec": "h264", "audio_codec": None}

    return probe


def _validate(
    zip_path: Path,
    *,
    final_duration: float = 3.0,
    segment_durations: dict[str, float] | None = None,
    unplayable: set[str] | None = None,
    audio_codec: str = "mp3",
) -> list[str]:
    return validate_export_zip(
        zip_path,
        job_id="job-001",
        media_probe=_media_probe(
            final_duration=final_duration,
            segment_durations=segment_durations,
            unplayable=unplayable,
            audio_codec=audio_codec,
        ),
    )


def _make_zip(zip_path: Path, files: dict[str, str | bytes]) -> None:
    """Create a ZIP file with the given name→content mapping."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            if isinstance(content, str):
                zf.writestr(name, content)
            else:
                zf.writestr(name, content)


def _make_valid_timeline(
    segment_count: int = 3,
) -> str:
    segments = [
        {
            "kind": "montage",
            "start_ms": i * 3000,
            "end_ms": (i + 1) * 3000,
            "sentence_index": i,
            "text": f"sentence {i}",
            "rendered_file": f"final/seg_{i + 1:03d}.mp4",
        }
        for i in range(segment_count)
    ]
    return json.dumps(
        {
            "version": "2.0",
            "duration_ms": segment_count * 3000,
            "fingerprint": "fp-test",
            "segments": segments,
        }
    )


class TestValidateExportZip:
    """Content-level validation of the export ZIP."""

    def test_valid_zip_with_matching_segments_passes(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"fake video data",
                "export_job-001/final/seg_001.mp4": b"seg 1",
                "export_job-001/final/seg_002.mp4": b"seg 2",
                "export_job-001/final/seg_003.mp4": b"seg 3",
                "export_job-001/audio/tts.mp3": b"audio data",
                "export_job-001/subtitle/script.srt": "1\n00:00:00,000 --> 00:00:03,000\nhello\n",
                "export_job-001/timeline.json": _make_valid_timeline(3),
            },
        )
        errors = _validate(zip_path, final_duration=9.0)
        assert errors == []

    def test_missing_final_video_detected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/seg_001.mp4": b"seg 1",
                "export_job-001/timeline.json": _make_valid_timeline(1),
            },
        )
        errors = _validate(zip_path)
        assert any("final video" in e.lower() for e in errors)

    def test_missing_timeline_detected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"fake video",
                "export_job-001/final/seg_001.mp4": b"seg 1",
            },
        )
        errors = _validate(zip_path)
        assert any("timeline" in e.lower() for e in errors)

    def test_segment_count_mismatch_detected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"fake video",
                "export_job-001/final/seg_001.mp4": b"seg 1",
                "export_job-001/final/seg_002.mp4": b"seg 2",
                "export_job-001/timeline.json": _make_valid_timeline(3),
            },
        )
        errors = _validate(zip_path, final_duration=9.0)
        assert any("segment count" in e.lower() for e in errors)
        assert any("2 segments" in e for e in errors)

    def test_empty_segment_detected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"fake video",
                "export_job-001/final/seg_001.mp4": b"",
                "export_job-001/timeline.json": _make_valid_timeline(1),
            },
        )
        errors = _validate(zip_path)
        assert any("empty" in e.lower() for e in errors)

    def test_empty_final_video_detected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"",
                "export_job-001/final/seg_001.mp4": b"seg 1",
                "export_job-001/timeline.json": _make_valid_timeline(1),
            },
        )
        errors = _validate(zip_path)
        assert any("video is empty" in e.lower() for e in errors)

    def test_invalid_timeline_json_detected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"fake video",
                "export_job-001/final/seg_001.mp4": b"seg 1",
                "export_job-001/timeline.json": "not valid json",
            },
        )
        errors = _validate(zip_path)
        assert any("json" in e.lower() for e in errors)

    def test_timeline_missing_segments_field_detected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"fake video",
                "export_job-001/final/seg_001.mp4": b"seg 1",
                "export_job-001/timeline.json": json.dumps(
                    {"version": "2.0", "duration_ms": 3000}
                ),
            },
        )
        errors = _validate(zip_path)
        assert any("segments" in e.lower() for e in errors)

    def test_segment_naming_not_sequential_detected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"fake video",
                "export_job-001/final/seg_001.mp4": b"seg 1",
                "export_job-001/final/seg_003.mp4": b"seg 3",
                "export_job-001/timeline.json": _make_valid_timeline(2),
            },
        )
        errors = _validate(zip_path, final_duration=6.0)
        assert any("sequential" in e.lower() or "order" in e.lower() for e in errors), (
            errors
        )

    def test_rendered_file_must_reference_the_matching_zip_entry(
        self, tmp_path: Path
    ) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        timeline = json.loads(_make_valid_timeline(1))
        timeline["segments"][0]["rendered_file"] = "final/seg_005.mp4"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"video",
                "export_job-001/final/seg_001.mp4": b"segment",
                "export_job-001/timeline.json": json.dumps(timeline),
            },
        )

        errors = _validate(zip_path)

        assert any("rendered_file" in error for error in errors)

    def test_unplayable_final_video_is_rejected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"not video",
                "export_job-001/final/seg_001.mp4": b"segment",
                "export_job-001/timeline.json": _make_valid_timeline(1),
            },
        )

        errors = _validate(zip_path, unplayable={"final.mp4"})

        assert any("final video" in error and "probe" in error for error in errors)

    def test_unplayable_segment_is_rejected(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"video",
                "export_job-001/final/seg_001.mp4": b"not video",
                "export_job-001/timeline.json": _make_valid_timeline(1),
            },
        )

        errors = _validate(zip_path, unplayable={"seg_001.mp4"})

        assert any("seg_001.mp4" in error and "playable" in error for error in errors)

    def test_segment_duration_must_match_timeline(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"video",
                "export_job-001/final/seg_001.mp4": b"segment",
                "export_job-001/timeline.json": _make_valid_timeline(1),
            },
        )

        errors = _validate(
            zip_path,
            segment_durations={"seg_001.mp4": 1.5},
        )

        assert any("duration mismatch" in error for error in errors)

    def test_segment_durations_must_collectively_cover_final_video(
        self, tmp_path: Path
    ) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"video",
                "export_job-001/final/seg_001.mp4": b"segment 1",
                "export_job-001/final/seg_002.mp4": b"segment 2",
                "export_job-001/timeline.json": _make_valid_timeline(2),
            },
        )

        errors = _validate(
            zip_path,
            final_duration=6.0,
            segment_durations={"seg_001.mp4": 2.8, "seg_002.mp4": 2.8},
        )

        assert any("segment coverage mismatch" in error for error in errors)

    def test_non_object_segment_returns_errors_instead_of_crashing(
        self, tmp_path: Path
    ) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        timeline = json.loads(_make_valid_timeline(1))
        timeline["segments"] = ["not-an-object"]
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"video",
                "export_job-001/final/seg_001.mp4": b"segment",
                "export_job-001/timeline.json": json.dumps(timeline),
            },
        )

        errors = _validate(zip_path)

        assert any("not an object" in error for error in errors)

    def test_timeline_must_continuously_cover_final_video(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        timeline = json.loads(_make_valid_timeline(2))
        timeline["segments"][1]["start_ms"] = 4000
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"video",
                "export_job-001/final/seg_001.mp4": b"segment 1",
                "export_job-001/final/seg_002.mp4": b"segment 2",
                "export_job-001/timeline.json": json.dumps(timeline),
            },
        )

        errors = _validate(zip_path, final_duration=7.0)

        assert any("timeline gap" in error for error in errors)

    def test_audio_extension_must_match_codec(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "export_job-001.zip"
        _make_zip(
            zip_path,
            {
                "export_job-001/final/final.mp4": b"video",
                "export_job-001/final/seg_001.mp4": b"segment",
                "export_job-001/audio/tts.wav": b"actually mp3",
                "export_job-001/timeline.json": _make_valid_timeline(1),
            },
        )

        errors = _validate(zip_path, audio_codec="mp3")

        assert any("audio encoding mismatch" in error for error in errors)
