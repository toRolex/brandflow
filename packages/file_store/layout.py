"""Workspace layout seam — single source of truth for project-tree paths.

This module is intentionally pure: the ``WorkspaceLayout`` class does no
filesystem I/O at construction or during method calls.  Every method returns
a :class:`pathlib.Path` that the caller may ``.exists()`` / ``.mkdir()`` /
``.glob()`` directly.  Path input validation is structural and lexical —
the layout never invokes ``Path.resolve()`` (which would resolve symlinks
and interact with the filesystem).

Contract highlights:

* Identifiers (``project_id`` / ``job_id`` / ``name`` / ``asset_name``) are
  rejected when they are empty, ``None``, contain ``/`` or ``\\``, contain
  a ``.`` segment (``"."`` or ``".."``), or are absolute.  Unicode, spaces,
  hyphens, and underscores are allowed.
* Relative paths (``workspace_relative_path`` / ``job_artifact_path``)
  accept both ``/`` and ``\\`` separators but reject absolute inputs,
  empty inputs, ``None``, and any ``..`` segment after lexical splitting.
  Containment is verified via :meth:`Path.is_relative_to`, never via
  ``resolve()``.
* All rejection paths raise :class:`InvalidWorkspacePath` (a
  :class:`ValueError` subclass) so callers can catch a single surface.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Final


class InvalidWorkspacePath(ValueError):
    """Raised when an identifier or relative path fails lexical validation.

    Inherits from :class:`ValueError` so production code can catch a single
    exception type regardless of which kind of input failed validation.
    """


class AmbiguousJobError(Exception):
    """Raised when a ``job_id`` resolves to more than one Project.

    The workspace structure is well-formed; the conflict is semantic.
    Callers typically translate this to ``HTTP 409``.
    """


# Separator characters that, when present in an identifier, indicate a
# caller is trying to inject a path traversal or escape the project tree.
_FORBIDDEN_IDENTIFIER_SEPARATORS: Final = ("/", "\\")


def _validate_identifier(value: object, *, field: str) -> str:
    """Validate an identifier string and return it unchanged on success.

    Rules:

    * Must be a ``str`` (not ``None``).
    * Must not be empty.
    * Must not contain ``/`` or ``\\``.
    * Must not equal ``"."`` or ``".."``.
    * Must not be an absolute path (POSIX or Windows).
    """
    if value is None:
        raise InvalidWorkspacePath(f"{field} must not be None")
    if not isinstance(value, str):
        raise InvalidWorkspacePath(
            f"{field} must be a string, got {type(value).__name__}"
        )
    if value == "":
        raise InvalidWorkspacePath(f"{field} must not be empty")
    if value in (".", ".."):
        raise InvalidWorkspacePath(f"{field} must not be '.' or '..' (got {value!r})")
    for separator in _FORBIDDEN_IDENTIFIER_SEPARATORS:
        if separator in value:
            raise InvalidWorkspacePath(
                f"{field} must not contain separator {separator!r} (got {value!r})"
            )
    if value.startswith("/") or value.startswith("\\"):
        raise InvalidWorkspacePath(
            f"{field} must not be an absolute path (got {value!r})"
        )
    # Windows drive-letter form (e.g. ``C:\\foo`` or ``C:/foo``).
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        raise InvalidWorkspacePath(
            f"{field} must not be a Windows absolute path (got {value!r})"
        )
    return value


def _validate_relative_path(value: object, *, field: str) -> str:
    """Validate a relative path string and normalise its separators.

    The input is rejected when it is ``None``, empty, absolute, or contains
    a ``..`` segment after splitting on either separator.  Callers that need
    ``Path`` objects should pass the returned string to :class:`pathlib.Path`
    after combining with the layout root.
    """
    if value is None:
        raise InvalidWorkspacePath(f"{field} must not be None")
    if not isinstance(value, str):
        raise InvalidWorkspacePath(
            f"{field} must be a string, got {type(value).__name__}"
        )
    if value == "":
        raise InvalidWorkspacePath(f"{field} must not be empty")
    # POSIX absolute: ``/foo``; Windows absolute: ``\\foo`` or ``C:\\foo``.
    if value.startswith("/"):
        raise InvalidWorkspacePath(
            f"{field} must not be a POSIX absolute path (got {value!r})"
        )
    if value.startswith("\\") or value.startswith("//"):
        raise InvalidWorkspacePath(
            f"{field} must not be a Windows absolute path (got {value!r})"
        )
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        raise InvalidWorkspacePath(
            f"{field} must not be a Windows absolute path (got {value!r})"
        )
    # Reject ``..`` segments after lexical splitting.  We split on both
    # ``/`` and ``\\`` so a Windows caller cannot smuggle a ``..`` via the
    # backslash separator.
    normalised = value.replace("\\", "/")
    for segment in normalised.split("/"):
        if segment in ("", "."):
            # Empty segments (from leading or trailing ``/``) and ``.`` are
            # treated as lexical no-ops and accepted; ``..`` is rejected
            # below.
            continue
        if segment == "..":
            raise InvalidWorkspacePath(
                f"{field} must not contain '..' segment (got {value!r})"
            )
    return normalised


class WorkspaceLayout:
    """Lexical seam for every project-tree path under a workspace root.

    The layout is the only place where the on-disk directory structure is
    documented.  All other modules call semantic methods (``project_dir``,
    ``job_runtime_dir``, ``source_asset_path``, ...) and never concatenate
    path strings manually.
    """

    __slots__ = ("_root", "root")

    def __init__(self, root: Path) -> None:
        """Store *root* verbatim.  No I/O is performed."""
        self._root = root
        # ``root`` is exposed read-only via the public attribute.  We do not
        # use ``@property`` because the value is immutable for the lifetime
        # of the layout instance.
        self.root = root

    # ------------------------------------------------------------------
    # Top-level paths
    # ------------------------------------------------------------------

    def workspace_dir(self) -> Path:
        """Return the workspace root directory itself."""
        return self._root

    def projects_dir(self) -> Path:
        """Return the directory that holds all Project trees."""
        return self._root / "workspace" / "projects"

    # ------------------------------------------------------------------
    # Project-level paths
    # ------------------------------------------------------------------

    def project_dir(self, project_id: str) -> Path:
        pid = _validate_identifier(project_id, field="project_id")
        return self.projects_dir() / pid

    def project_meta_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project_meta.json"

    def control_jobs_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "control" / "jobs"

    def control_batches_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "control" / "batches"

    def reviews_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "reviews"

    def review_events_path(self, project_id: str) -> Path:
        return self.reviews_dir(project_id) / "review_events.jsonl"

    def reports_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "reports"

    def logs_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "logs"

    # ------------------------------------------------------------------
    # Runtime assets and audio
    # ------------------------------------------------------------------

    def audio_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "runtime" / "audio"

    def audio_path(self, project_id: str, name: str) -> Path:
        return self.audio_dir(project_id) / _validate_identifier(name, field="name")

    def source_assets_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "runtime" / "source_assets"

    def source_asset_path(self, project_id: str, name: str) -> Path:
        return self.source_assets_dir(project_id) / _validate_identifier(
            name, field="asset_name"
        )

    def indexed_clips_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "runtime" / "indexed_clips"

    def runtime_exports_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "runtime" / "exports"

    def schedule_exports_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "runtime" / "schedule" / "exports"

    # ------------------------------------------------------------------
    # Job-level paths
    # ------------------------------------------------------------------

    def job_record_path(self, project_id: str, job_id: str) -> Path:
        pid = _validate_identifier(project_id, field="project_id")
        jid = _validate_identifier(job_id, field="job_id")
        return self.control_jobs_dir(pid) / f"{jid}.json"

    def job_runtime_dir(self, project_id: str, job_id: str) -> Path:
        pid = _validate_identifier(project_id, field="project_id")
        jid = _validate_identifier(job_id, field="job_id")
        return self.project_dir(pid) / "runtime" / "jobs" / jid

    def job_artifact_path(
        self, project_id: str, job_id: str, relative_path: str
    ) -> Path:
        """Return a path inside the Job runtime directory.

        ``relative_path`` accepts both ``/`` and ``\\`` separators and must
        not escape the runtime directory.  Containment is verified via
        :meth:`Path.is_relative_to`; we never call ``resolve()`` so the
        check is purely lexical and cannot be influenced by symlinks.
        """
        runtime_dir = self.job_runtime_dir(project_id, job_id)
        normalised = _validate_relative_path(relative_path, field="relative_path")
        candidate = runtime_dir / PurePosixPath(normalised)
        if not candidate.is_relative_to(runtime_dir):
            raise InvalidWorkspacePath(
                f"relative_path escapes job runtime dir (got {relative_path!r})"
            )
        return candidate

    # ------------------------------------------------------------------
    # Workspace-relative paths
    # ------------------------------------------------------------------

    def workspace_relative_path(self, relative_path: str) -> Path:
        """Resolve a workspace-relative path against the layout root.

        Used for the ``/workspace/<relative-path>`` URL contract consumed by
        the frontend: callers pass the storage-relative portion and the
        layout joins it under the workspace root.
        """
        normalised = _validate_relative_path(relative_path, field="relative_path")
        candidate = self._root / PurePosixPath(normalised)
        if not candidate.is_relative_to(self._root):
            raise InvalidWorkspacePath(
                f"relative_path escapes workspace root (got {relative_path!r})"
            )
        return candidate


__all__ = [
    "AmbiguousJobError",
    "InvalidWorkspacePath",
    "WorkspaceLayout",
]
