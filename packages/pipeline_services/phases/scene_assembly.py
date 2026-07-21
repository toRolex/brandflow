"""Scene assembly phase handler (import mode)."""

from __future__ import annotations

import json as _json
import random
import shutil as _shutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from packages.pipeline_services.phase_orchestrator import (
        PhaseContext,
        PhaseOrchestrator,
    )


def run(orchestrator: PhaseOrchestrator, ctx: PhaseContext) -> list:
    """scene_assembling: build scene segment from scene folders with crossfade transitions.

    Reads scene folder paths from ``ctx.scene_folder_paths`` (populated by
    the tick service) or falls back to ``ctx.scene_config`` or ConfigReader.
    Picks one random video file from each folder, then uses ffmpeg ``xfade``
    to create a crossfade scene segment.
    """
    workspace_dir = ctx.root_dir / "workspace"
    job_dir = orchestrator._job_dir(ctx)

    # 1. Resolve scene folder paths
    folders = _resolve_scene_folders(ctx)

    if not folders:
        print(f"[SCENE] No scene folders configured for {ctx.job_id}", flush=True)
        return []

    # 2. Check for existing snapshot (deterministic re-render, Issue #174)
    snapshot_dir = job_dir / ".scene_snapshot"
    manifest_path = snapshot_dir / "manifest.json"
    force_reselect: bool = ctx.options.get("force_reselect", False)
    clips: list[Path] = []

    if manifest_path.exists() and not force_reselect:
        # Verify source file fingerprints per-entry (issue #227 / #174 AC-6)
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        valid_entries: list[int] = []  # indices whose fingerprint still matches
        invalid_entries: list[int] = []  # indices whose source has changed
        for idx, entry in enumerate(manifest):
            src = Path(entry["source"])
            if src.exists():
                st = src.stat()
                if st.st_size == entry["size"] and st.st_mtime == entry["mtime"]:
                    valid_entries.append(idx)
                else:
                    # mtime-based fingerprint; content hash if drift
                    invalid_entries.append(idx)
            else:
                # missing source = snapshot still valid (we have the local copy)
                valid_entries.append(idx)

        if invalid_entries:
            print(
                f"[SCENE] {len(invalid_entries)}/{len(manifest)} source fingerprints "
                f"changed, re-randomizing only those entries",
                flush=True,
            )

        for idx in valid_entries:
            local_path = snapshot_dir / manifest[idx]["local"]
            if local_path.exists():
                clips.append(local_path)

        # Re-randomize only the invalidated entries from their source folders
        if invalid_entries:
            for idx in invalid_entries:
                if idx < len(folders) and folders[idx].exists():
                    candidates = _scene_candidates(folders[idx])
                    if candidates:
                        clips.insert(idx, random.choice(candidates))
                    else:
                        # Fallback: use existing snapshot even if stale
                        local_path = snapshot_dir / manifest[idx]["local"]
                        if local_path.exists():
                            clips.insert(idx, local_path)
                else:
                    local_path = snapshot_dir / manifest[idx]["local"]
                    if local_path.exists():
                        clips.insert(idx, local_path)

        if clips:
            print(
                f"[SCENE] Using snapshot ({len(valid_entries)} cached + "
                f"{len(invalid_entries)} re-randomized)",
                flush=True,
            )

        # Update snapshot for re-randomized entries
        if invalid_entries:
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            for idx in invalid_entries:
                if idx < len(clips):
                    clip = clips[idx]
                    local_name = f"{idx}{clip.suffix}"
                    _shutil.copy2(clip, snapshot_dir / local_name)
                    st = clip.stat()
                    found = False
                    for entry in manifest:
                        if entry["local"] == manifest[idx]["local"]:
                            entry.update(
                                {
                                    "source": str(clip.resolve()),
                                    "local": local_name,
                                    "size": st.st_size,
                                    "mtime": st.st_mtime,
                                }
                            )
                            found = True
                            break
                    if not found:
                        manifest.append(
                            {
                                "source": str(clip.resolve()),
                                "local": local_name,
                                "size": st.st_size,
                                "mtime": st.st_mtime,
                            }
                        )
            (snapshot_dir / "manifest.json").write_text(
                _json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    if not clips:
        # Fully fresh selection: every entry was invalid or no manifest
        for folder in folders:
            if not folder.exists():
                print(f"[SCENE] Folder not found: {folder}", flush=True)
                continue
            candidates = _scene_candidates(folder)
            if not candidates:
                print(f"[SCENE] No video files in {folder}", flush=True)
                continue
            clips.append(random.choice(candidates))

        if not clips:
            print(f"[SCENE] No clips found for {ctx.job_id}", flush=True)
            return []

        print(f"[SCENE] {len(clips)} clips selected for {ctx.job_id}", flush=True)
        for c in clips:
            print(f"[SCENE]   {c}", flush=True)

        # Snapshot: copy selected clips to job-owned .scene_snapshot/
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        manifest = []
        for i, clip in enumerate(clips):
            local_name = f"{i}{clip.suffix}"
            _shutil.copy2(clip, snapshot_dir / local_name)
            st = clip.stat()
            manifest.append(
                {
                    "source": str(clip.resolve()),
                    "local": local_name,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                }
            )
        (snapshot_dir / "manifest.json").write_text(
            _json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[SCENE] Snapshot saved: {len(manifest)} clips → {snapshot_dir}",
            flush=True,
        )

    transition_duration = ctx.transition_duration_ms / 1000.0
    scene_path = job_dir / "scene_segment.mp4"

    if len(clips) == 1:
        # Single clip -- copy directly
        _shutil.copy2(clips[0], scene_path)
        print(f"[SCENE] Single clip copied to {scene_path}", flush=True)
    else:
        # Build ffmpeg xfade chain
        ffmpeg = orchestrator._get_ffmpeg_path()
        durations = [orchestrator._get_media_duration(c) for c in clips]

        # Filter chain: settb on all inputs, then chained xfade
        filter_parts: list[str] = []
        accumulated = durations[0]
        for i in range(1, len(clips)):
            offset = accumulated - transition_duration
            prev_label = f"r{i - 1}" if i > 1 else "c0"
            cur_in_label = f"c{i}"
            out_label = f"t{i}"

            # Build segments
            filter_parts.append(
                f"[{i}:v]settb=AVTB,fps=30,scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2[{cur_in_label}]"
            )
            filter_parts.append(
                f"[{prev_label}][{cur_in_label}]"
                f"xfade=transition=fade:duration={transition_duration:.3f}:"
                f"offset={offset:.3f}[{out_label}]"
            )
            if i < len(clips) - 1:
                filter_parts.append(f"[{out_label}]setpts=PTS-STARTPTS,fps=30[r{i}]")

            accumulated += durations[i] - transition_duration

        # First input always needs settb + fps + scale normalization
        filter_complex = (
            "[0:v]settb=AVTB,fps=30,scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2[c0];"
            + ";".join(filter_parts)
        )
        final_label = f"t{len(clips) - 1}"

        cmd = [ffmpeg, "-y"]
        for clip in clips:
            cmd.extend(["-i", str(clip)])
        cmd.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                f"[{final_label}]",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(scene_path),
            ]
        )

        print(f"[SCENE] Running ffmpeg xfade for {len(clips)} clips", flush=True)
        import subprocess

        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)

    if scene_path.exists():
        print(
            f"[SCENE] scene_segment.mp4 produced ({scene_path.stat().st_size} bytes)",
            flush=True,
        )
        return [orchestrator._to_artifact("scene_segment", scene_path, workspace_dir)]
    return []


def _resolve_scene_folders(ctx: PhaseContext, config_reader=None) -> list[Path]:
    """Resolve scene folder paths from context, config or ConfigReader."""
    folders: list[Path] = []
    if ctx.scene_folder_paths:
        for folder_path in ctx.scene_folder_paths:
            path = Path(folder_path)
            if not path.is_absolute():
                path = ctx.root_dir / "workspace" / path
            folders.append(path)
        return folders

    scene_config = ctx.scene_config
    if not scene_config and config_reader is not None:
        scene_config = config_reader.get_scene_config(product_id=ctx.product)
    for entry in scene_config.get("folders", []):
        path_str = entry.get("path", "")
        if path_str:
            folders.append(ctx.root_dir / "workspace" / path_str)
    return folders


def _scene_candidates(folder: Path) -> list[Path]:
    """Return usable video files inside a scene folder."""
    if not folder.exists() or not folder.is_dir():
        return []
    video_ext = {".mp4", ".mov", ".avi"}
    return [
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in video_ext
    ]
