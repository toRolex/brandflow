"""GET /api/check-version, POST /api/update, and GET /api/update/status endpoints."""

import json
import re
import subprocess
import sys
import time as _time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from apps.control_plane._version import get_version

router = APIRouter(tags=["version"])

_GIT_REMOTE = "origin"

# ponytail: global lock, per-account locks if throughput matters
_update_in_progress: bool = False
_update_process: subprocess.Popen | None = None

_UPDATE_STALLED_SECONDS: int = 120  # 2 min for POST conflict detection
_STARTUP_RESET_SECONDS: int = 300  # 5 min for lifespan cleanup


def _is_windows() -> bool:
    return sys.platform == "win32"


def _progress_path() -> Path | None:
    """Return the path to progress.json, or None if not on Windows."""
    if not _is_windows():
        return None
    root = Path(__file__).resolve().parent.parent.parent.parent
    return root / "packaging" / "windows" / "progress.json"


def _read_progress() -> dict | None:
    """Parse progress.json on disk.  Returns None when file missing or unreadable."""
    pp = _progress_path()
    if pp is None or not pp.exists():
        return None
    try:
        return json.loads(pp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cleanup_progress() -> None:
    """Remove progress.json if it exists."""
    pp = _progress_path()
    if pp is not None and pp.exists():
        pp.unlink(missing_ok=True)


def _reset_update_lock() -> None:
    """Reset the in-memory update lock and process handle."""
    global _update_in_progress, _update_process
    _update_in_progress = False
    _update_process = None


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


def _progress_conflict() -> JSONResponse | None:
    """Check progress.json for conflicts before starting an update.

    Returns a 409 conflict response, or None when safe to proceed.
    """
    progress = _read_progress()
    if progress is None:
        return None

    status = progress.get("status", "")
    updated_at = progress.get("updated_at", "")

    if status in ("running", "restarting"):
        if not _is_stalled(updated_at, _UPDATE_STALLED_SECONDS):
            return JSONResponse(
                content={
                    "status": "in_progress",
                    "detail": f"更新正在进行中 (step={progress.get('step')})",
                },
                status_code=409,
            )
        # stalled — allow retry

    # failed / done / stalled — clean up and allow retry
    _cleanup_progress()
    return None


def _is_stalled(updated_at: str, threshold_seconds: int) -> bool:
    """Return True when *updated_at* is older than *threshold_seconds*."""
    if not updated_at:
        return True  # missing timestamp → treat as stalled
    try:
        dt = datetime.fromisoformat(updated_at)
    except (ValueError, TypeError):
        # Non-ISO format (Windows %date% %time% is not ISO 8601) → best effort
        return True
    return (_time.time() - dt.timestamp()) > threshold_seconds


def _write_initial_progress() -> None:
    """Write the initial progress.json state before launching update.bat."""
    pp = _progress_path()
    if pp is None:
        return
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.write_text(
        json.dumps(
            {
                "status": "running",
                "step": "git_pull",
                "step_label": "拉取最新代码",
                "percent": 5,
                "updated_at": _now_iso(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@router.get("/api/update/status")
def update_status() -> JSONResponse:
    """Return the current update progress, including stalled detection."""
    progress = _read_progress()
    if progress is None:
        return JSONResponse(content={"status": "idle"})

    status = progress.get("status", "")
    updated_at = progress.get("updated_at", "")

    if status in ("running", "restarting") and _is_stalled(
        updated_at, _UPDATE_STALLED_SECONDS
    ):
        progress["stalled"] = True

    return JSONResponse(content=progress)


@router.post("/api/update")
def trigger_update() -> JSONResponse:
    global _update_in_progress, _update_process

    # ── progress.json conflict detection ──
    conflict = _progress_conflict()
    if conflict is not None:
        return conflict

    # ── in-memory lock ──
    if _update_in_progress:
        if _update_process is not None and _update_process.poll() is not None:
            _reset_update_lock()
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

    # Write initial progress.json before launching update.bat
    _write_initial_progress()

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
