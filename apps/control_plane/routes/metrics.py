"""API routes for video metrics: upload, overview, videos, topics, scan."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from apps.control_plane.services.metrics import MetricsStore

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


def _store(request: Request) -> MetricsStore:
    """Create a MetricsStore bound to the app's data directory."""
    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "data" / "metrics.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return MetricsStore(db_path=str(db_path))


# ── Upload ────────────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_metrics(file: UploadFile, request: Request) -> dict[str, int]:
    """Upload a CSV (微信视频号) or XLSX (小红书) metrics file.

    Platform is auto-detected from the filename:
    - filename contains "视频号" -> weixin
    - filename ends with .xlsx -> xiaohongshu
    - fallback -> weixin
    """
    store = _store(request)
    filename = file.filename or ""
    content = await file.read()

    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    if filename.lower().endswith(".xlsx"):
        # Auto-detect: xlsx → xiaohongshu, unless "视频号" in name
        platform = "weixin" if "视频号" in filename else "xiaohongshu"

        # Write to temp file (import_xlsx expects a file path)
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        try:
            result = store.import_xlsx(tmp_path, platform=platform)
        finally:
            tmp_path.unlink(missing_ok=True)
    else:
        # Auto-detect: csv → weixin, unless filename hints otherwise
        platform = "weixin"
        if "小红书" in filename or "xhs" in filename.lower():
            platform = "xiaohongshu"
        result = store.import_csv(content, platform=platform, filename=filename)

    return result


# ── Overview ──────────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(
    request: Request,
    days: int = Query(default=7, ge=1, le=365),
    platform: str | None = Query(default=None),
) -> dict[str, Any]:
    """Aggregate metrics overview for the last N days."""
    store = _store(request)
    return store.get_overview(days=days, platform=platform)


# ── Videos ────────────────────────────────────────────────────────────────────────

@router.get("/videos")
def get_videos(
    request: Request,
    sort_by: str = Query(default="plays_desc"),
    platform: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Paginated, sorted video list with optional search."""
    store = _store(request)
    return store.get_videos(
        sort_by=sort_by, platform=platform, search=search,
        page=page, page_size=page_size,
    )


# ── Topics ────────────────────────────────────────────────────────────────────────

@router.get("/topics")
def get_topics(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    platform: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Top keywords by total plays extracted from video titles."""
    store = _store(request)
    return store.get_topics(days=days, platform=platform, limit=limit)


# ── Scan ──────────────────────────────────────────────────────────────────────────

@router.post("/scan")
def scan_data_directory(request: Request) -> dict[str, Any]:
    """Recursively scan the data/ directory for .csv and .xlsx files and import them.

    Platform is inferred from the directory structure:
    - path contains 'weixin' -> weixin
    - path contains 'xiaohongshu' or 'xhs' -> xiaohongshu
    - .xlsx without platform hint -> xiaohongshu
    - .csv without platform hint -> weixin
    """
    store = _store(request)
    root_dir: Path = request.app.state.root_dir
    data_dir = root_dir / "data"

    if not data_dir.exists():
        return {"files_processed": 0, "total_inserted": 0, "total_updated": 0, "files": []}

    files_processed = 0
    total_inserted = 0
    total_updated = 0
    file_details: list[dict[str, Any]] = []

    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in (".csv", ".xlsx"):
            continue

        rel = str(path.relative_to(data_dir)).lower()
        if "weixin" in rel or "视频号" in rel:
            platform = "weixin"
        elif "xiaohongshu" in rel or "xhs" in rel:
            platform = "xiaohongshu"
        elif ext == ".xlsx":
            platform = "xiaohongshu"
        else:
            platform = "weixin"

        try:
            if ext == ".xlsx":
                result = store.import_xlsx(path, platform=platform)
            else:
                result = store.import_csv(path.read_bytes(), platform=platform,
                                          filename=path.name)
            files_processed += 1
            total_inserted += result.get("inserted", 0)
            total_updated += result.get("updated", 0)
            file_details.append({"file": str(path), "result": result})
        except Exception as e:
            file_details.append({"file": str(path), "error": str(e)})

    return {
        "files_processed": files_processed,
        "total_inserted": total_inserted,
        "total_updated": total_updated,
        "files": file_details,
    }
