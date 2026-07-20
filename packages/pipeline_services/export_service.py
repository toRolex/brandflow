"""Export bundle ZIP packaging for completed jobs.

Builds an export ZIP containing all intermediate production artifacts
for secondary editing in professional software (DaVinci Resolve, Premiere Pro).
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path
from typing import Any, Callable

from packages.pipeline_services.segment_export import (
    build_timeline_2,
    segment_final_video,
)

ALLOWED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".webm"})


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

        # 2. Audio track (prefer wav, fall back to mp3 renamed)
        _add_audio_to_zip(job_dir, zf, zip_prefix)

        # 3. Subtitle file (skip if not present)
        srt_path = job_dir / "subtitles.srt"
        if srt_path.exists():
            zf.write(srt_path, f"{zip_prefix}subtitle/script.srt")

        # 4. Source clips — scene (from config folders) + montage (from selected_clips.json)
        _add_source_clips_to_zip(job_dir, workspace_dir, zf, zip_prefix, scene_cfg)

        # 5. Precise per-segment chunks (seg_NNN.mp4) split from final.mp4 on the
        #    Final Timeline boundaries (issue #181), plus the flat 2.0 timeline.
        if final_path.exists():
            seg_dir = export_dir / f".segs_{job_id}"
            try:
                for seg_path in segment_final_video(
                    final_path, final_timeline.get("segments", []), seg_dir
                ):
                    zf.write(seg_path, f"{zip_prefix}final/{seg_path.name}")
            finally:
                shutil.rmtree(seg_dir, ignore_errors=True)

        zf.writestr(
            f"{zip_prefix}timeline.json",
            json.dumps(timeline_2, ensure_ascii=False, indent=2),
        )

    return zip_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _add_audio_to_zip(job_dir: Path, zf: zipfile.ZipFile, zip_prefix: str) -> None:
    """Add audio file to the ZIP, preserving the actual encoding extension.

    WAV and MP3 files keep their true extensions so the ZIP content is
    honest about the encoding.  WAV → ``tts.wav``, MP3 → ``tts.mp3``.
    """
    wav_path = job_dir / "audio.wav"
    mp3_path = job_dir / "audio.mp3"

    if wav_path.exists():
        zf.write(wav_path, f"{zip_prefix}audio/tts.wav")
    elif mp3_path.exists():
        zf.write(mp3_path, f"{zip_prefix}audio/tts.mp3")


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
        except Exception:
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

    # Montage clips from selected_clips.json
    clip_list_path = job_dir / "selected_clips.json"
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
        except Exception:
            pass
