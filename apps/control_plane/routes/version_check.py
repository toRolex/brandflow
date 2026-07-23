"""GET /api/check-version and POST /api/update endpoints."""

import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from apps.control_plane._version import get_version

router = APIRouter(tags=["version"])

_GIT_REMOTE = "origin"

# ponytail: global lock, per-account locks if throughput matters
_update_in_progress: bool = False
_update_process: subprocess.Popen | None = None


def _is_windows() -> bool:
    return sys.platform == "win32"


def _parse_version(v: str) -> tuple[int, ...]:
    """Convert '0.7.13' to (0, 7, 13) for comparison."""
    return tuple(int(p) for p in v.strip().lstrip("v").split("."))


def _latest_git_tag(project_root: Path | None = None) -> str:
    """Return the newest semver tag from the git remote, stripped of leading 'v'.

    Uses ``git ls-remote --tags`` instead of the GitHub REST API to avoid
    unauthenticated rate limiting when the service runs behind a shared
    proxy (e.g. Clash on the production Windows machine).
    """
    cwd = project_root or Path(__file__).resolve().parent.parent.parent.parent
    result = subprocess.run(
        ["git", "ls-remote", "--tags", _GIT_REMOTE],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(cwd),
    )
    result.check_returncode()
    # Extract tag names, strip leading 'v', pick the highest semver.
    tags: list[tuple[int, ...]] = []
    for line in result.stdout.splitlines():
        m = re.search(r"refs/tags/(v?\d+\.\d+\.\d+)(\^\{\})?$", line)
        if m:
            tags.append(_parse_version(m.group(1)))
    return ".".join(str(p) for p in max(tags)) if tags else ""


@router.get("/api/check-version")
async def check_version() -> JSONResponse:
    current = get_version()
    try:
        latest = _latest_git_tag()
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


@router.post("/api/update")
def trigger_update() -> JSONResponse:
    global _update_in_progress, _update_process

    if _update_in_progress:
        if _update_process is not None and _update_process.poll() is not None:
            # previous process exited, reset and allow a new update
            _update_in_progress = False
            _update_process = None
        else:
            return JSONResponse(
                content={"status": "in_progress"},
                status_code=409,
            )

    if not _is_windows():
        return JSONResponse(
            content={"status": "error", "message": "更新仅支持 Windows 平台"},
            status_code=400,
        )

    _update_in_progress = True

    root = Path(__file__).resolve().parent.parent.parent.parent
    bat_path = root / "packaging/windows/update.bat"
    log_path = root / "packaging/windows/update.log"

    with open(log_path, "a") as log:
        _update_process = subprocess.Popen(
            [str(bat_path)],
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=str(root),
        )

    return JSONResponse(
        content={"status": "started", "log": "packaging/windows/update.log"}
    )
