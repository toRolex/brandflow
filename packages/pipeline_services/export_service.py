"""Export bundle ZIP packaging for completed jobs.

Builds an export ZIP containing all intermediate production artifacts
for secondary editing in professional software (DaVinci Resolve, Premiere Pro).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable

from packages.pipeline_services.media_probe import probe_media
from packages.pipeline_services.media_utils import get_ffmpeg_path
from packages.pipeline_services.segment_export import (
    build_timeline_2,
    segment_final_video,
)

ALLOWED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".webm"})
FINAL_VIDEO_PROGRESS = 10
AUDIO_PROGRESS = 20
SUBTITLE_PROGRESS = 30
SOURCE_CLIPS_PROGRESS = 40
SEGMENTS_PROGRESS_RANGE = 50
SEGMENTS_COMPLETE_PROGRESS = SOURCE_CLIPS_PROGRESS + SEGMENTS_PROGRESS_RANGE
BUNDLE_COMPLETE_PROGRESS = 100


class RerenderRequiredError(RuntimeError):
    """Raised when a job has no render-time Final Timeline to segment against."""


def _get_scene_config_default() -> dict[str, Any]:
    """Default scene config provider — reads from ConfigReader."""
    from packages.provider_config.config_reader import ConfigReader

    return ConfigReader().get_scene_config()


def build_export_bundle(
    job_dir: Path,
    workspace_dir: Path,
    project_dir: Path,
    export_dir: Path,
    *,
    get_scene_config: Callable[[], dict[str, Any]] | None = None,
    progress_callback: Callable[[int], None] | None = None,
) -> Path:
    """Build export bundle ZIP for a completed job.

    Reads job artifacts from *job_dir* and packages them with a clean
    directory structure.  Returns the path to the generated ZIP file.

    ZIP structure::

        export_{job_id}/
        ├── final/
        │   └── final.mp4
        ├── source_clips/
        │   ├── scene_001.mp4
        │   ├── scene_002.mp4
        │   └── montage_001.mp4
        ├── audio/
        │   └── tts.wav
        ├── subtitle/
        │   └── script.srt
        └── timeline.json
    """
    if get_scene_config is None:
        get_scene_config = _get_scene_config_default
    report_progress = progress_callback or (lambda _percent: None)
    scene_cfg = get_scene_config()

    # Export requires the authoritative render-time Final Timeline (issue #179);
    # a legacy job without one must be re-rendered before it can be exported.
    final_timeline_path = job_dir / "final_timeline.json"
    if not final_timeline_path.exists():
        raise RerenderRequiredError(
            f"job {job_dir.name} has no Final Timeline; re-render before export"
        )
    final_timeline = json.loads(final_timeline_path.read_text(encoding="utf-8"))
    timeline_2 = build_timeline_2(final_timeline)

    job_id = job_dir.name
    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = export_dir / f"export_{job_id}.zip"
    zip_prefix = f"export_{job_id}/"

    final_path = job_dir / "final.mp4"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Final rendered video
        if final_path.exists():
            zf.write(final_path, f"{zip_prefix}final/final.mp4")
        report_progress(FINAL_VIDEO_PROGRESS)

        # 2. Audio track (prefer wav, fall back to mp3 renamed)
        _add_audio_to_zip(job_dir, zf, zip_prefix)
        report_progress(AUDIO_PROGRESS)

        # 3. Subtitle file (skip if not present)
        srt_path = job_dir / "subtitles.srt"
        if srt_path.exists():
            zf.write(srt_path, f"{zip_prefix}subtitle/script.srt")
        report_progress(SUBTITLE_PROGRESS)

        # 4. Source clips — scene (from config folders) + montage (from selected_clips.json)
        _add_source_clips_to_zip(job_dir, workspace_dir, zf, zip_prefix, scene_cfg)
        report_progress(SOURCE_CLIPS_PROGRESS)

        # 5. Precise per-segment chunks (seg_NNN.mp4) split from final.mp4 on the
        #    Final Timeline boundaries (issue #181), plus the flat 2.0 timeline.
        if final_path.exists():
            seg_dir = export_dir / f".segs_{job_id}"
            try:
                for seg_path in segment_final_video(
                    final_path,
                    final_timeline.get("segments", []),
                    seg_dir,
                    progress_callback=lambda percent: report_progress(
                        SOURCE_CLIPS_PROGRESS
                        + round(percent / 100 * SEGMENTS_PROGRESS_RANGE)
                    ),
                ):
                    zf.write(seg_path, f"{zip_prefix}final/{seg_path.name}")
            finally:
                shutil.rmtree(seg_dir, ignore_errors=True)
        report_progress(SEGMENTS_COMPLETE_PROGRESS)

        zf.writestr(
            f"{zip_prefix}timeline.json",
            json.dumps(timeline_2, ensure_ascii=False, indent=2),
        )
        report_progress(BUNDLE_COMPLETE_PROGRESS)

    return zip_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _add_audio_to_zip(job_dir: Path, zf: zipfile.ZipFile, zip_prefix: str) -> None:
    """Add audio with a filename that truthfully describes its encoding."""
    wav_path = job_dir / "audio.wav"
    mp3_path = job_dir / "audio.mp3"
    source = wav_path if wav_path.exists() else mp3_path
    if not source.exists():
        return

    codec = probe_media(source)["audio_codec"]
    if codec == "mp3":
        zf.write(source, f"{zip_prefix}audio/tts.mp3")
        return
    if codec and codec.startswith("pcm_"):
        zf.write(source, f"{zip_prefix}audio/tts.wav")
        return
    if codec is None:
        # Preserve legacy/unprobeable artifacts for diagnosis. The task-level
        # validator rejects them before the ZIP can become downloadable.
        zf.write(source, f"{zip_prefix}audio/tts{source.suffix.lower()}")
        return

    with tempfile.TemporaryDirectory(prefix="brandflow-export-audio-") as tmp:
        converted = Path(tmp) / "tts.wav"
        subprocess.run(
            [
                get_ffmpeg_path(),
                "-y",
                "-i",
                str(source),
                "-vn",
                "-c:a",
                "pcm_s16le",
                str(converted),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        zf.write(converted, f"{zip_prefix}audio/tts.wav")


def _add_source_clips_to_zip(
    job_dir: Path,
    workspace_dir: Path,
    zf: zipfile.ZipFile,
    zip_prefix: str,
    scene_cfg: dict[str, Any],
) -> None:
    """Enumerate scene + montage clips and write them into the ZIP.

    Scene clips come first (``scene_001``, ``scene_002``, …) followed by
    montage clips (``montage_001``, …).

    When a ``.scene_snapshot/manifest.json`` exists (issue #174), scene clips
    are read from the snapshot to match the actual rendered frames instead of
    enumerating the full scene folders (issue #227 / #181 AC-7).
    """
    clip_counter = 1

    # Scene clips: prefer snapshot manifest, fall back to config folders
    snapshot_manifest_path = job_dir / ".scene_snapshot" / "manifest.json"
    if snapshot_manifest_path.exists():
        try:
            manifest = json.loads(snapshot_manifest_path.read_text(encoding="utf-8"))
            for entry in manifest:
                clip_path = job_dir / ".scene_snapshot" / entry["local"]
                if clip_path.exists():
                    ext = clip_path.suffix.lower()
                    arc_name = f"{zip_prefix}source_clips/scene_{clip_counter:03d}{ext}"
                    zf.write(clip_path, arc_name)
                    clip_counter += 1
        except (json.JSONDecodeError, OSError, TypeError, UnicodeDecodeError):
            pass
    else:
        # Fallback: enumerate scene config folders
        for entry in scene_cfg.get("folders", []):
            folder_path_str = entry.get("path", "")
            if not folder_path_str:
                continue
            folder = workspace_dir / folder_path_str
            if not folder.exists():
                continue
            for f in sorted(folder.iterdir()):
                if f.is_file() and f.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS:
                    arc_name = (
                        f"{zip_prefix}source_clips/scene_{clip_counter:03d}{f.suffix}"
                    )
                    zf.write(f, arc_name)
                    clip_counter += 1

    # Montage clips — prefer the immutable reviewed snapshot (#249)
    # Fall back to selected_clips.json for jobs approved before the
    # reviewed snapshot was introduced.
    snapshot_path = job_dir / "reviewed_assets.json"
    clip_list_path = (
        snapshot_path if snapshot_path.exists() else job_dir / "selected_clips.json"
    )
    if clip_list_path.exists():
        try:
            selected: list[dict[str, Any]] = json.loads(
                clip_list_path.read_text(encoding="utf-8")
            )
            for item in selected:
                file_path = item.get("file_path", "")
                if not file_path:
                    continue
                src = Path(file_path)
                if not src.exists():
                    src = workspace_dir / file_path
                if not src.exists():
                    continue
                arc_name = (
                    f"{zip_prefix}source_clips/montage_{clip_counter:03d}{src.suffix}"
                )
                zf.write(src, arc_name)
                clip_counter += 1
        except (json.JSONDecodeError, OSError, TypeError, UnicodeDecodeError):
            pass
