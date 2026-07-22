"""GET /api/check-version — compare current version against latest GitHub tag."""

import requests

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from apps.control_plane._version import get_version

router = APIRouter(tags=["version"])

_GITHUB_TAGS_URL = "https://api.github.com/repos/toRolex/brandflow/tags"
_TIMEOUT = 5  # seconds


def _parse_version(v: str) -> tuple[int, ...]:
    """Convert '0.7.13' to (0, 7, 13) for comparison."""
    return tuple(int(p) for p in v.strip().lstrip("v").split("."))


def _latest_github_tag() -> str:
    """Fetch newest tag name from GitHub, stripped of leading 'v'."""
    resp = requests.get(_GITHUB_TAGS_URL, timeout=_TIMEOUT)
    resp.raise_for_status()
    tags = resp.json()
    # ponytail: first tag from the list is most recent (GitHub returns sorted)
    return tags[0]["name"].lstrip("v") if tags else ""


@router.get("/api/check-version")
async def check_version() -> JSONResponse:
    current = get_version()
    try:
        latest = _latest_github_tag()
        update_available = bool(latest) and _parse_version(latest) > _parse_version(
            current
        )
    except Exception:
        # ponytail: network/GitHub failures silently return no update
        latest = ""
        update_available = False
    return JSONResponse(
        content={
            "current": current,
            "latest": latest,
            "update_available": update_available,
        },
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )
