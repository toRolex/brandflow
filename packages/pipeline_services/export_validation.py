"""Content and media validation for export ZIP bundles (#255)."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from packages.pipeline_services.media_probe import MediaInfo, probe_media

MEDIA_DURATION_TOLERANCE_SECONDS = 0.25


MediaProbe = Callable[[Path], MediaInfo]


def validate_export_zip(
    zip_path: Path,
    *,
    job_id: str,
    media_probe: MediaProbe | None = None,
) -> list[str]:
    """Return actionable errors for an export ZIP, or an empty list when valid."""
    if not zip_path.exists():
        return ["ZIP file does not exist"]

    probe = media_probe or probe_media
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            prefix = f"export_{job_id}/"
            errors: list[str] = []

            final_entry = f"{prefix}final/final.mp4"
            errors.extend(_check_nonempty_entry(zf, final_entry, "final video"))
            timeline, timeline_errors = _read_timeline(zf, prefix, names)
            errors.extend(timeline_errors)

            if timeline is None:
                return errors

            segments = timeline["segments"]
            segment_entries = sorted(
                name for name in names if name.startswith(f"{prefix}final/seg_")
            )
            errors.extend(_check_segment_count(segment_entries, segments))
            errors.extend(_check_segment_naming_sequential(segment_entries))
            errors.extend(
                _check_rendered_file_references(prefix, segment_entries, segments)
            )
            for entry in segment_entries:
                errors.extend(
                    _check_nonempty_entry(zf, entry, f"segment {Path(entry).name}")
                )

            with tempfile.TemporaryDirectory(
                prefix="brandflow-export-validate-"
            ) as tmp:
                temp_dir = Path(tmp)
                media_info: dict[str, MediaInfo] = {}
                media_entries = [final_entry, *segment_entries]
                audio_entries = sorted(
                    name for name in names if name.startswith(f"{prefix}audio/tts.")
                )
                if not audio_entries:
                    errors.append("missing audio track in export bundle")
                elif len(audio_entries) > 1:
                    errors.append("multiple audio tracks found in export bundle")
                media_entries.extend(audio_entries)

                for index, entry in enumerate(media_entries):
                    if entry not in names or zf.getinfo(entry).file_size == 0:
                        continue
                    extracted = _copy_entry_for_probe(zf, entry, temp_dir, index)
                    media_info[entry] = probe(extracted)

                final_info = media_info.get(final_entry)
                errors.extend(_check_final_video_probe(final_info))
                errors.extend(
                    _check_segment_media(
                        prefix,
                        segment_entries,
                        segments,
                        media_info,
                    )
                )
                errors.extend(
                    _check_segment_total_duration(
                        segment_entries,
                        final_info,
                        media_info,
                    )
                )
                errors.extend(_check_timeline_coverage(segments, final_info))
                errors.extend(_check_audio_encoding(prefix, audio_entries, media_info))

            return errors
    except zipfile.BadZipFile:
        return ["ZIP file is corrupt (not a valid ZIP)"]


def _copy_entry_for_probe(
    zf: zipfile.ZipFile,
    entry: str,
    temp_dir: Path,
    index: int,
) -> Path:
    """Copy a ZIP entry to a controlled filename without extracting paths."""
    output = temp_dir / f"{index:04d}" / Path(entry).name
    output.parent.mkdir()
    with zf.open(entry) as source, output.open("wb") as target:
        shutil.copyfileobj(source, target)
    return output


def _check_nonempty_entry(
    zf: zipfile.ZipFile,
    entry: str,
    label: str,
) -> list[str]:
    try:
        if zf.getinfo(entry).file_size == 0:
            return [f"{label} is empty (0 bytes)"]
    except KeyError:
        return [f"missing {label} in export bundle"]
    return []


def _read_timeline(
    zf: zipfile.ZipFile,
    prefix: str,
    names: set[str],
) -> tuple[dict | None, list[str]]:
    entry = f"{prefix}timeline.json"
    if entry not in names:
        return None, ["missing timeline.json in export bundle"]
    try:
        data = json.loads(zf.read(entry).decode("utf-8"))
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None, ["timeline.json is not valid JSON"]
    if not isinstance(data, dict):
        return None, ["timeline.json root is not an object"]
    if not isinstance(data.get("segments"), list):
        return None, ["timeline.json missing valid 'segments' list"]

    errors: list[str] = []
    for index, segment in enumerate(data["segments"]):
        if not isinstance(segment, dict):
            errors.append(f"timeline segment {index} is not an object")
            continue
        if not isinstance(segment.get("rendered_file"), str):
            errors.append(f"timeline segment {index} missing 'rendered_file' field")
        if not isinstance(segment.get("start_ms"), (int, float)) or not isinstance(
            segment.get("end_ms"), (int, float)
        ):
            errors.append(f"timeline segment {index} has invalid time bounds")
    return data, errors


def _check_segment_count(seg_files: list[str], segments: list[dict]) -> list[str]:
    if len(seg_files) == len(segments):
        return []
    return [
        f"segment count mismatch: {len(seg_files)} segments for "
        f"{len(segments)} timeline entries"
    ]


def _check_segment_naming_sequential(seg_files: list[str]) -> list[str]:
    expected = [f"seg_{index:03d}.mp4" for index in range(1, len(seg_files) + 1)]
    actual = [Path(entry).name for entry in seg_files]
    if actual == expected:
        return []
    return ["segment file numbering is not sequential starting from 1"]


def _check_rendered_file_references(
    prefix: str,
    seg_files: list[str],
    segments: list[dict],
) -> list[str]:
    actual = [entry.removeprefix(prefix) for entry in seg_files]
    referenced = [
        segment.get("rendered_file") if isinstance(segment, dict) else None
        for segment in segments
    ]
    if referenced == actual:
        return []
    return [
        "timeline rendered_file references do not match ZIP segments in playback order"
    ]


def _check_final_video_probe(info: MediaInfo | None) -> list[str]:
    if info is None:
        return []
    if info["video_codec"] is None or info["duration"] is None:
        return ["final video could not be probed as playable video"]
    return []


def _check_segment_media(
    prefix: str,
    seg_files: list[str],
    segments: list[dict],
    media_info: dict[str, MediaInfo],
) -> list[str]:
    errors: list[str] = []
    by_rendered_file = {
        segment.get("rendered_file"): segment
        for segment in segments
        if isinstance(segment, dict)
    }
    for entry in seg_files:
        info = media_info.get(entry)
        if info is None:
            continue
        name = Path(entry).name
        if info["video_codec"] is None or info["duration"] is None:
            errors.append(f"segment {name} is not playable video")
            continue
        segment = by_rendered_file.get(entry.removeprefix(prefix))
        if not segment:
            continue
        start_ms = segment.get("start_ms")
        end_ms = segment.get("end_ms")
        if not isinstance(start_ms, (int, float)) or not isinstance(
            end_ms, (int, float)
        ):
            continue
        expected = (end_ms - start_ms) / 1000
        if abs(info["duration"] - expected) > MEDIA_DURATION_TOLERANCE_SECONDS:
            errors.append(
                f"segment {name} duration mismatch: probed {info['duration']:.3f}s, "
                f"timeline expects {expected:.3f}s"
            )
    return errors


def _check_timeline_coverage(
    segments: list[dict],
    final_info: MediaInfo | None,
) -> list[str]:
    if not segments:
        if final_info and final_info["duration"] not in (None, 0):
            return ["timeline has no segments but final video has content"]
        return []

    errors: list[str] = []
    previous_end = 0.0
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        start = segment.get("start_ms")
        end = segment.get("end_ms")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            continue
        if start > previous_end:
            errors.append(
                f"timeline gap before segment {index}: {start - previous_end:.0f}ms"
            )
        elif start < previous_end:
            errors.append(
                f"timeline overlap before segment {index}: {previous_end - start:.0f}ms"
            )
        if end <= start:
            errors.append(f"timeline segment {index} has non-positive duration")
        previous_end = end

    final_duration = final_info["duration"] if final_info else None
    if final_duration is not None and abs(previous_end / 1000 - final_duration) > (
        MEDIA_DURATION_TOLERANCE_SECONDS
    ):
        errors.append(
            f"timeline coverage mismatch: ends at {previous_end / 1000:.3f}s, "
            f"final video is {final_duration:.3f}s"
        )
    return errors


def _check_segment_total_duration(
    seg_files: list[str],
    final_info: MediaInfo | None,
    media_info: dict[str, MediaInfo],
) -> list[str]:
    final_duration = final_info["duration"] if final_info else None
    durations = [
        media_info[entry]["duration"]
        for entry in seg_files
        if entry in media_info and media_info[entry]["duration"] is not None
    ]
    if final_duration is None or len(durations) != len(seg_files):
        return []
    segment_duration = sum(duration for duration in durations if duration is not None)
    if abs(segment_duration - final_duration) <= MEDIA_DURATION_TOLERANCE_SECONDS:
        return []
    return [
        f"segment coverage mismatch: segments total {segment_duration:.3f}s, "
        f"final video is {final_duration:.3f}s"
    ]


def _check_audio_encoding(
    prefix: str,
    audio_entries: list[str],
    media_info: dict[str, MediaInfo],
) -> list[str]:
    errors: list[str] = []
    for entry in audio_entries:
        info = media_info.get(entry)
        if info is None:
            continue
        codec = info["audio_codec"]
        relative = entry.removeprefix(prefix)
        if codec is None:
            errors.append(f"audio track {relative} is not probeable")
        elif entry.endswith(".mp3") and codec != "mp3":
            errors.append(
                f"audio encoding mismatch: {relative} contains {codec}, expected mp3"
            )
        elif entry.endswith(".wav") and not codec.startswith("pcm_"):
            errors.append(
                f"audio encoding mismatch: {relative} contains {codec}, expected PCM WAV"
            )
    return errors
