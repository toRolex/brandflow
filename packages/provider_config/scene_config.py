"""Validation shared by every scene-configuration write path."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.file_store.layout import InvalidWorkspacePath, WorkspaceLayout


class SceneConfigValidationError(ValueError):
    """Raised when a scene folder configuration cannot stay in workspace."""


def validate_scene_folders(value: Any, root_dir: Path) -> None:
    """Require a list of objects with workspace-relative non-empty paths."""
    if not isinstance(value, list):
        raise SceneConfigValidationError("scene.folders must be an array")

    layout = WorkspaceLayout(root_dir)
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise SceneConfigValidationError(
                f"scene.folders[{index}] must be an object"
            )
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise SceneConfigValidationError(f"scene.folders[{index}].path is required")
        try:
            layout.workspace_relative_path(path)
        except InvalidWorkspacePath as exc:
            raise SceneConfigValidationError(
                f"invalid path: scene.folders[{index}]"
            ) from exc


def validate_scene_payload(payload: dict, root_dir: Path) -> None:
    """Validate ``scene.folders`` inside a config payload dict.

    No-op when *payload* has no scene section.  Raises
    ``SceneConfigValidationError`` when any folder path is invalid.
    """
    scene = payload.get("scene") if isinstance(payload, dict) else None
    if not isinstance(scene, dict) or "folders" not in scene:
        return
    validate_scene_folders(scene["folders"], root_dir)
