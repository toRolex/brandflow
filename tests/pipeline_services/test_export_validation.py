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
        errors = validate_export_zip(zip_path, job_id="job-001")
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
        errors = validate_export_zip(zip_path, job_id="job-001")
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
        errors = validate_export_zip(zip_path, job_id="job-001")
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
        errors = validate_export_zip(zip_path, job_id="job-001")
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
        errors = validate_export_zip(zip_path, job_id="job-001")
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
        errors = validate_export_zip(zip_path, job_id="job-001")
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
        errors = validate_export_zip(zip_path, job_id="job-001")
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
        errors = validate_export_zip(zip_path, job_id="job-001")
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
        errors = validate_export_zip(zip_path, job_id="job-001")
        assert any("sequential" in e.lower() or "order" in e.lower() for e in errors), (
            errors
        )
