"""Shared asset-review validation and snapshot logic (#254).

Used by both the human-approval API endpoint and the auto-approval path
in the tick service, so both paths perform the same checks and write the
same reviewed snapshot.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class AssetValidationError(Exception):
    """Raised when the asset selection fails integrity checks."""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def validate_assets(job_dir: Path, *, force: bool = False) -> list[dict[str, Any]]:
    """Validate selected_clips.json integrity and return the parsed clips.

    Returns:
        The parsed clip list (list of dict).

    Raises:
        AssetValidationError: when integrity checks fail:
          - unresolved clips present (409)
          - all-blank without force (409)
        FileNotFoundError: when selected_clips.json does not exist.
    """
    clips_path = job_dir / "selected_clips.json"
    if not clips_path.exists():
        raise FileNotFoundError(f"selected_clips.json not found: {clips_path}")

    clips: list[dict[str, Any]] = json.loads(clips_path.read_text(encoding="utf-8"))

    # Check for unresolved clips
    unresolved = [c for c in clips if c.get("visual_type") == "unresolved"]
    if unresolved:
        raise AssetValidationError(
            f"尚有 {len(unresolved)} 个句子素材未解决（unresolved），请先处理",
            status_code=409,
        )

    # Check all-blank without force
    has_clip = any(c.get("visual_type") == "clip" for c in clips)
    if not has_clip and not force:
        raise AssetValidationError(
            "所有素材均为空白（blank），确认后请使用 force=true",
            status_code=409,
        )

    return clips


def write_reviewed_snapshot(job_dir: Path, clips: list[dict[str, Any]]) -> Path:
    """Write the reviewed_assets.json snapshot.

    The snapshot includes the full clip list with script sentence text,
    sentence_index, visual_type, asset identity, and media metadata.

    Args:
        job_dir: Job runtime directory.
        clips: The validated clip list to snapshot.

    Returns:
        Path to the written snapshot file.
    """
    snapshot_path = job_dir / "reviewed_assets.json"
    snapshot_path.write_text(
        json.dumps(clips, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"[AssetSnapshot] reviewed_assets.json written: {snapshot_path}")
    return snapshot_path


def validate_and_snapshot_assets(
    job_dir: Path, *, force: bool = False
) -> tuple[list[dict[str, Any]], Path]:
    """Validate asset selection integrity and write the reviewed snapshot.

    This is the single entry point that both human-approval (API) and
    auto-approval (tick service) call to ensure identical behavior.

    Returns:
        (clips, snapshot_path)

    Raises:
        AssetValidationError: when integrity checks fail.
        FileNotFoundError: when selected_clips.json does not exist.
    """
    clips = validate_assets(job_dir, force=force)
    snapshot_path = write_reviewed_snapshot(job_dir, clips)
    return clips, snapshot_path
