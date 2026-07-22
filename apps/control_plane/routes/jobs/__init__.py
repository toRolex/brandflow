"""Nested FastAPI routers for job-related API endpoints."""

from apps.control_plane.routes.jobs import content
from apps.control_plane.routes.jobs import cover_title
from apps.control_plane.routes.jobs import crud
from apps.control_plane.routes.jobs import export
from apps.control_plane.routes.jobs import metadata
from apps.control_plane.routes.jobs import migration
from apps.control_plane.routes.jobs import tts

__all__ = [
    "content",
    "cover_title",
    "crud",
    "export",
    "metadata",
    "migration",
    "tts",
]
