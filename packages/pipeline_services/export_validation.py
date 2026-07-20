"""Content-level validation for export ZIP bundles (#255).

Verifies the internal structure of an export ZIP before marking the task ready:
final video present, timeline valid JSON with proper schema, segment file count
matches timeline entries, all segment files are non-empty, and segment naming
follows sequential ``seg_NNN.mp4`` numbering.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


def validate_export_zip(zip_path: Path, *, job_id: str) -> list[str]:
    """Validate the export ZIP's content integrity.

    Returns a list of human-readable error strings. An empty list means the
    ZIP passes all content checks and is safe to publish as ready.
    """
    if not zip_path.exists():
        return ["ZIP file does not exist"]

    errors: list[str] = []

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            prefix = f"export_{job_id}/"

            # 1. Final video must exist and be non-zero.
            _check_final_video(zf, prefix, names, errors)

            # 2. Timeline must exist and be valid JSON with segments.
            timeline_data = _check_timeline(zf, prefix, names, errors)

            if timeline_data is not None:
                segments: list[dict] = timeline_data.get("segments", [])

                # 3. Segment file count must match timeline segment count.
                seg_files = sorted(
                    n for n in names if n.startswith(f"{prefix}final/seg_")
                )
                _check_segment_count(seg_files, segments, errors)

                # 4. Each segment file must be non-empty.
                _check_segments_nonempty(zf, seg_files, errors)

                # 5. Segment naming must be sequential (seg_001, seg_002, ...).
                _check_segment_naming_sequential(seg_files, errors)
    except zipfile.BadZipFile:
        return ["ZIP file is corrupt (not a valid ZIP)"]

    return errors


# ---------------------------------------------------------------------------
# Internal check helpers
# ---------------------------------------------------------------------------


def _check_final_video(
    zf: zipfile.ZipFile,
    prefix: str,
    names: set[str],
    errors: list[str],
) -> None:
    final_video_entry = f"{prefix}final/final.mp4"
    if final_video_entry not in names:
        errors.append("missing final video (final/final.mp4) in export bundle")
        return
    try:
        info = zf.getinfo(final_video_entry)
        if info.file_size == 0:
            errors.append("final video is empty (0 bytes)")
    except KeyError:
        errors.append("final video entry missing in ZIP index")


def _check_timeline(
    zf: zipfile.ZipFile,
    prefix: str,
    names: set[str],
    errors: list[str],
) -> dict | None:
    timeline_entry = f"{prefix}timeline.json"
    if timeline_entry not in names:
        errors.append("missing timeline.json in export bundle")
        return None

    try:
        raw = zf.read(timeline_entry)
    except Exception:
        errors.append("failed to read timeline.json from ZIP")
        return None

    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        errors.append("timeline.json is not valid JSON")
        return None

    # Validate required fields per timeline 2.0 schema.
    if "segments" not in data:
        errors.append("timeline.json missing 'segments' field")
    elif not isinstance(data["segments"], list):
        errors.append("timeline.json 'segments' field is not a list")

    # Validate each segment has a rendered_file reference.
    segments: list[dict] = data.get("segments", [])
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            errors.append(f"timeline segment {i} is not an object")
            continue
        if "rendered_file" not in seg:
            errors.append(f"timeline segment {i} missing 'rendered_file' field")

    return data


def _check_segment_count(
    seg_files: list[str],
    segments: list[dict],
    errors: list[str],
) -> None:
    if len(seg_files) != len(segments):
        errors.append(
            f"segment count mismatch: {len(seg_files)} segments for "
            f"{len(segments)} timeline entries"
        )


def _check_segments_nonempty(
    zf: zipfile.ZipFile,
    seg_files: list[str],
    errors: list[str],
) -> None:
    for seg_name in seg_files:
        try:
            info = zf.getinfo(seg_name)
            if info.file_size == 0:
                errors.append(f"segment {Path(seg_name).name} is empty (0 bytes)")
        except KeyError:
            errors.append(f"segment {Path(seg_name).name} missing from ZIP index")


def _check_segment_naming_sequential(
    seg_files: list[str],
    errors: list[str],
) -> None:
    """Verify segment files follow seg_001, seg_002, ... naming.

    The files are already sorted alphabetically; we check that their numeric
    suffixes form a contiguous sequence starting at 1.
    """
    indices: list[int] = []
    for f in seg_files:
        name = Path(f).stem  # e.g. "seg_001"
        try:
            num = int(name.split("_")[-1])
            indices.append(num)
        except (ValueError, IndexError):
            errors.append(f"segment file {name} has unexpected name format")
            return

    expected = list(range(1, len(indices) + 1))
    if indices != expected:
        errors.append("segment file numbering is not sequential starting from 1")
