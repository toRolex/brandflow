"""Export bundle ZIP packaging for completed jobs.

Builds an export ZIP containing all intermediate production artifacts
for secondary editing in professional software (DaVinci Resolve, Premiere Pro).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any, Callable

ALLOWED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".webm"})


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

    job_id = job_dir.name
    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = export_dir / f"export_{job_id}.zip"
    zip_prefix = f"export_{job_id}/"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. Final rendered video
        final_path = job_dir / "final.mp4"
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

        # 5. Generated timeline description
        timeline = generate_timeline_json(
            job_dir, workspace_dir, project_dir, scene_cfg=scene_cfg
        )
        zf.writestr(
            f"{zip_prefix}timeline.json",
            json.dumps(timeline, ensure_ascii=False, indent=2),
        )

    return zip_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _add_audio_to_zip(job_dir: Path, zf: zipfile.ZipFile, zip_prefix: str) -> None:
    """Add audio file to the ZIP.

    Prefers ``audio.wav``; if only ``audio.mp3`` exists it is copied but
    named ``tts.wav`` inside the ZIP (standard format per the PRD).
    """
    wav_path = job_dir / "audio.wav"
    mp3_path = job_dir / "audio.mp3"

    if wav_path.exists():
        zf.write(wav_path, f"{zip_prefix}audio/tts.wav")
    elif mp3_path.exists():
        zf.write(mp3_path, f"{zip_prefix}audio/tts.wav")


def _add_source_clips_to_zip(
    job_dir: Path,
    workspace_dir: Path,
    zf: zipfile.ZipFile,
    zip_prefix: str,
    scene_cfg: dict[str, Any],
) -> None:
    """Enumerate scene + montage clips and write them into the ZIP.

    Scene clips come first (``scene_001``, ``scene_002``, …) followed by
    montage clips (``montage_001``, …).  The same numbering order is used
    by ``generate_timeline_json`` to produce matching references.
    """
    clip_counter = 1

    # Scene clips from config scene folders
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


def generate_timeline_json(
    job_dir: Path,
    workspace_dir: Path,
    project_dir: Path,  # noqa: ARG001  -- kept for API stability
    *,
    scene_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate *timeline.json* describing the edit decision list.

    The returned dict is serialised into the ZIP as ``timeline.json``.
    File references use ZIP-relative paths (e.g. ``source_clips/scene_001.mp4``)
    so the file is self-contained when extracted.
    """
    if scene_cfg is None:
        scene_cfg = _get_scene_config_default()

    segments: list[dict[str, Any]] = []
    clip_counter = 1
    transition_duration_ms = scene_cfg.get("transition_duration_ms", 500)

    # 1. Scene clips segment
    scene_clips: list[dict[str, Any]] = []
    for entry in scene_cfg.get("folders", []):
        folder_path_str = entry.get("path", "")
        if not folder_path_str:
            continue
        folder = workspace_dir / folder_path_str
        if not folder.exists():
            continue
        for f in sorted(folder.iterdir()):
            if f.is_file() and f.suffix.lower() in ALLOWED_VIDEO_EXTENSIONS:
                scene_clips.append(
                    {
                        "file": f"source_clips/scene_{clip_counter:03d}{f.suffix}",
                        "duration_ms": _try_get_duration_ms(f),
                        "transition": "crossfade",
                        "transition_duration_ms": transition_duration_ms,
                    }
                )
                clip_counter += 1

    if scene_clips:
        segments.append({"type": "scene", "clips": scene_clips})

    # 2. Montage clips segment
    montage_clips: list[dict[str, Any]] = []
    clip_list_path = job_dir / "selected_clips.json"
    if clip_list_path.exists():
        try:
            selected: list[dict[str, Any]] = json.loads(
                clip_list_path.read_text(encoding="utf-8")
            )
            for idx, item in enumerate(selected):
                file_path = item.get("file_path", "")
                if not file_path:
                    continue
                src = Path(file_path)
                if not src.exists():
                    src = workspace_dir / file_path
                if not src.exists():
                    continue
                duration_ms = _try_get_duration_ms(src)
                montage_clips.append(
                    {
                        "file": f"source_clips/montage_{clip_counter:03d}{src.suffix}",
                        "in_point_ms": 0,
                        "out_point_ms": duration_ms,
                        "sentence_index": idx,
                    }
                )
                clip_counter += 1
        except Exception:
            pass

    if montage_clips:
        segments.append({"type": "montage", "clips": montage_clips})

    # 3. Audio metadata
    audio: dict[str, Any] = {"file": "audio/tts.wav"}
    wav_path = job_dir / "audio.wav"
    mp3_path = job_dir / "audio.mp3"
    audio_src: Path | None = None
    if wav_path.exists():
        audio_src = wav_path
    elif mp3_path.exists():
        audio_src = mp3_path
    if audio_src is not None:
        audio["duration_ms"] = _try_get_duration_ms(audio_src)

    # 4. Subtitle metadata (optional)
    timeline: dict[str, Any] = {
        "version": "1.0",
        "segments": segments,
        "audio": audio,
    }
    srt_path = job_dir / "subtitles.srt"
    if srt_path.exists():
        timeline["subtitle"] = {"file": "subtitle/script.srt"}

    return timeline


def _try_get_duration_ms(path: Path) -> int:
    """Return media duration in milliseconds, or 0 on error."""
    try:
        from packages.pipeline_services.media_utils import get_media_duration

        seconds = get_media_duration(path)
        return int(seconds * 1000)
    except Exception:
        return 0
