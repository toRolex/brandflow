"""Unit tests for ``WorkspaceLayout``.

These tests intentionally avoid any filesystem I/O (no ``tmp_path``, no
``mkdir``).  ``WorkspaceLayout`` is a pure lexical seam: every assertion
verifies that the returned ``pathlib.Path`` is structurally correct, not
that the path exists on disk.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from packages.file_store.layout import (
    AmbiguousJobError,
    InvalidWorkspacePath,
    WorkspaceLayout,
)


# ---------------------------------------------------------------------------
# Constructor and exports
# ---------------------------------------------------------------------------


def test_invalid_workspace_path_is_value_error() -> None:
    """``InvalidWorkspacePath`` is a ``ValueError`` subclass so callers can
    catch a single surface for both identifier and relative-path rejections."""
    assert issubclass(InvalidWorkspacePath, ValueError)


def test_ambiguous_job_error_is_exception() -> None:
    """``AmbiguousJobError`` is a bare ``Exception`` subclass — not a
    ``ValueError`` — because the workspace structure is well-formed but
    semantically ambiguous."""
    assert issubclass(AmbiguousJobError, Exception)


def test_constructor_does_not_perform_io(tmp_path: Path) -> None:
    """Constructing a layout does not touch the filesystem.  The directory
    is removed before construction to prove construction does not require
    it to exist."""
    shutil.rmtree(tmp_path)
    assert not tmp_path.exists()
    WorkspaceLayout(tmp_path)
    # constructor returns; nothing was created
    assert not tmp_path.exists()


def test_root_is_stored_as_private_field(tmp_path: Path) -> None:
    """The root path is preserved verbatim and exposed for callers that need
    a stable identifier; it is not exposed as a public mutable attribute."""
    layout = WorkspaceLayout(tmp_path)
    assert layout.root == tmp_path
    assert isinstance(layout.root, Path)


# ---------------------------------------------------------------------------
# Top-level paths
# ---------------------------------------------------------------------------


def test_workspace_dir_is_root() -> None:
    layout = WorkspaceLayout(Path("/workspace-root"))
    assert layout.workspace_dir() == Path("/workspace-root")
    assert layout.workspace_dir() == layout.root


def test_workspace_url_prefix_is_root_workspace() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.workspace_url_prefix() == Path("/root/workspace")


def test_projects_dir_is_workspace_projects() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.projects_dir() == Path("/root/workspace/projects")


# ---------------------------------------------------------------------------
# Project-level paths
# ---------------------------------------------------------------------------


def test_project_dir_returns_under_projects_dir() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.project_dir("project-001") == Path(
        "/root/workspace/projects/project-001"
    )


def test_project_meta_path_sits_inside_project_dir() -> None:
    layout = WorkspaceLayout(Path("/root"))
    meta = layout.project_meta_path("project-001")
    assert meta == Path("/root/workspace/projects/project-001/project_meta.json")
    assert meta.is_relative_to(layout.project_dir("project-001"))


def test_control_jobs_and_batches_dirs() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.control_jobs_dir("p1") == Path(
        "/root/workspace/projects/p1/control/jobs"
    )
    assert layout.control_batches_dir("p1") == Path(
        "/root/workspace/projects/p1/control/batches"
    )


def test_reviews_dir_and_review_events_path() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.reviews_dir("p1") == Path("/root/workspace/projects/p1/reviews")
    assert layout.review_events_path("p1") == Path(
        "/root/workspace/projects/p1/reviews/review_events.jsonl"
    )


def test_reports_and_logs_dirs() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.reports_dir("p1") == Path("/root/workspace/projects/p1/reports")
    assert layout.logs_dir("p1") == Path("/root/workspace/projects/p1/logs")


# ---------------------------------------------------------------------------
# Audio + source assets
# ---------------------------------------------------------------------------


def test_audio_dir_and_audio_path() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.audio_dir("p1") == Path("/root/workspace/projects/p1/runtime/audio")
    assert layout.audio_path("p1", "voice.mp3") == Path(
        "/root/workspace/projects/p1/runtime/audio/voice.mp3"
    )


def test_source_assets_dir_and_source_asset_path() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.source_assets_dir("p1") == Path(
        "/root/workspace/projects/p1/runtime/source_assets"
    )
    assert layout.source_asset_path("p1", "clip.mp4") == Path(
        "/root/workspace/projects/p1/runtime/source_assets/clip.mp4"
    )


def test_indexed_clips_dir() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.indexed_clips_dir("p1") == Path(
        "/root/workspace/projects/p1/runtime/indexed_clips"
    )


def test_runtime_exports_and_schedule_exports_dirs() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.runtime_exports_dir("p1") == Path(
        "/root/workspace/projects/p1/runtime/exports"
    )
    assert layout.schedule_exports_dir("p1") == Path(
        "/root/workspace/projects/p1/runtime/schedule/exports"
    )


# ---------------------------------------------------------------------------
# Job-level paths
# ---------------------------------------------------------------------------


def test_job_record_path() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.job_record_path("p1", "j1") == Path(
        "/root/workspace/projects/p1/control/jobs/j1.json"
    )


def test_job_runtime_dir() -> None:
    layout = WorkspaceLayout(Path("/root"))
    assert layout.job_runtime_dir("p1", "j1") == Path(
        "/root/workspace/projects/p1/runtime/jobs/j1"
    )


def test_job_artifact_path_accepts_relative_subpath() -> None:
    layout = WorkspaceLayout(Path("/root"))
    artifact = layout.job_artifact_path("p1", "j1", "subtitles/out.srt")
    assert artifact == Path(
        "/root/workspace/projects/p1/runtime/jobs/j1/subtitles/out.srt"
    )
    # The artifact must be lexically contained in the runtime dir.
    runtime = layout.job_runtime_dir("p1", "j1")
    assert artifact.is_relative_to(runtime)


# ---------------------------------------------------------------------------
# workspace_relative_path
# ---------------------------------------------------------------------------


def test_workspace_relative_path_joins_under_root() -> None:
    layout = WorkspaceLayout(Path("/root"))
    result = layout.workspace_relative_path("projects/p1/control/jobs/j1.json")
    assert result == Path("/root/projects/p1/control/jobs/j1.json")


def test_workspace_relative_path_accepts_backslash_separators() -> None:
    """Both ``/`` and ``\\`` separators are accepted so Windows and POSIX
    callers share the same interface."""
    layout = WorkspaceLayout(Path("/root"))
    result = layout.workspace_relative_path(r"projects\p1\control\jobs\j1.json")
    assert result == Path("/root/projects/p1/control/jobs/j1.json")


# ---------------------------------------------------------------------------
# Identifier validation — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "identifier",
    [
        "project-001",
        "job_42",
        "clip name.mp4",
        "中文项目",
        "Job-2026-01-15",
        "a",
        "1",
        "_underscore_start",
        "with spaces and-dashes_and_underscores",
    ],
)
def test_identifier_validation_accepts_unicode_spaces_and_separators(
    tmp_path: Path, identifier: str
) -> None:
    """Identifiers may contain Unicode characters, spaces, hyphens, and
    underscores; only structural separators (slashes, dots) are rejected."""
    layout = WorkspaceLayout(tmp_path)
    # Just touching the method is enough; we verify it returns a Path.
    result = layout.project_dir(identifier)
    assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# Identifier validation — rejection branches
# ---------------------------------------------------------------------------


def test_identifier_rejects_empty_string(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.project_dir("")


def test_identifier_rejects_none(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.project_dir(None)  # type: ignore[arg-type]


def test_identifier_rejects_forward_slash(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.project_dir("foo/bar")


def test_identifier_rejects_backslash(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.project_dir("foo\\bar")


def test_identifier_rejects_dot_segment(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.project_dir(".")


def test_identifier_rejects_double_dot_segment(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.project_dir("..")


def test_identifier_rejects_absolute_posix_path(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.project_dir("/etc/passwd")


def test_identifier_rejects_absolute_windows_path(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.project_dir(r"C:\Windows\System32")


def test_identifier_rejects_dot_segment_in_asset_name(tmp_path: Path) -> None:
    """A literal ``.`` segment is rejected: it would resolve to the asset
    directory itself, providing no useful filename."""
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.audio_path("p1", ".")


def test_identifier_rejects_slash_in_asset_name(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.audio_path("p1", "sub/dir/file.mp3")


def test_identifier_rejects_backslash_in_asset_name(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.audio_path("p1", "sub\\dir\\file.mp3")


def test_identifier_rejects_empty_asset_name(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.audio_path("p1", "")


def test_identifier_rejects_none_asset_name(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.audio_path("p1", None)  # type: ignore[arg-type]


def test_identifier_rejects_empty_job_id(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.job_runtime_dir("p1", "")


def test_identifier_rejects_absolute_job_id(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.job_record_path("p1", "/abs/job")


# ---------------------------------------------------------------------------
# Relative-path validation — rejection branches
# ---------------------------------------------------------------------------


def test_workspace_relative_path_rejects_absolute(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.workspace_relative_path("/etc/passwd")


def test_workspace_relative_path_rejects_dotdot_segment(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.workspace_relative_path("../etc/passwd")


def test_workspace_relative_path_rejects_empty(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.workspace_relative_path("")


def test_workspace_relative_path_rejects_none(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.workspace_relative_path(None)  # type: ignore[arg-type]


def test_job_artifact_path_rejects_absolute(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.job_artifact_path("p1", "j1", "/abs/file.txt")


def test_job_artifact_path_rejects_dotdot_segment(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.job_artifact_path("p1", "j1", "../escape.txt")


def test_job_artifact_path_rejects_empty(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    with pytest.raises(InvalidWorkspacePath):
        layout.job_artifact_path("p1", "j1", "")


def test_job_artifact_path_accepts_backslash_separators(tmp_path: Path) -> None:
    """Both ``/`` and ``\\`` separators are accepted so Windows callers can
    use the native separator."""
    layout = WorkspaceLayout(tmp_path)
    artifact = layout.job_artifact_path("p1", "j1", r"subtitles\out.srt")
    runtime = layout.job_runtime_dir("p1", "j1")
    assert artifact.is_relative_to(runtime)
    assert artifact == runtime / "subtitles" / "out.srt"


def test_job_artifact_path_accepts_nested_relative_paths(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    artifact = layout.job_artifact_path("p1", "j1", "a/b/c/d/e.txt")
    runtime = layout.job_runtime_dir("p1", "j1")
    assert artifact.is_relative_to(runtime)


# ---------------------------------------------------------------------------
# Workspace layout is read-only — no escape hatch
# ---------------------------------------------------------------------------


def test_layout_has_no_generic_join_method(tmp_path: Path) -> None:
    """The seam deliberately omits generic helpers (no ``join`` / ``path``)
    so callers cannot sidestep identifier validation."""
    layout = WorkspaceLayout(tmp_path)
    assert not hasattr(layout, "join")
    assert not hasattr(layout, "path")


# ---------------------------------------------------------------------------
# Path types are always pathlib.Path
# ---------------------------------------------------------------------------


def test_every_method_returns_pathlib_path(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    pid, jid, name, rel = "p1", "j1", "voice.mp3", "subtitles/out.srt"
    methods = [
        layout.workspace_dir(),
        layout.projects_dir(),
        layout.project_dir(pid),
        layout.project_meta_path(pid),
        layout.control_jobs_dir(pid),
        layout.control_batches_dir(pid),
        layout.reviews_dir(pid),
        layout.review_events_path(pid),
        layout.reports_dir(pid),
        layout.logs_dir(pid),
        layout.audio_dir(pid),
        layout.audio_path(pid, name),
        layout.source_assets_dir(pid),
        layout.source_asset_path(pid, name),
        layout.indexed_clips_dir(pid),
        layout.runtime_exports_dir(pid),
        layout.schedule_exports_dir(pid),
        layout.job_record_path(pid, jid),
        layout.job_runtime_dir(pid, jid),
        layout.job_artifact_path(pid, jid, rel),
        layout.workspace_relative_path("projects/p1/control/jobs/j1.json"),
    ]
    for value in methods:
        assert isinstance(value, Path), f"{value!r} is not a pathlib.Path"
