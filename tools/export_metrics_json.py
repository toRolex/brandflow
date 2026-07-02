"""Export metrics.db → JSON files for static GitHub Pages deployment.

Usage:
    uv run python tools/export_metrics_json.py            [--db PATH] [--out DIR]
    uv run python tools/export_metrics_json.py --save-snapshot YYYY-MM-DD [--out DIR]
    uv run python tools/export_metrics_json.py --current YYYY-MM-DD --previous YYYY-MM-DD [--out DIR]

This reads the same metrics.db used by the control plane and writes
overview.json, videos.json, and topics.json consumable by the
standalone AnalyticsStaticPage on GitHub Pages.

Snapshot flow (recommended — works with production UPSERT):
    1. Before importing new data:  run ``--save-snapshot YYYY-MM-DD``
    2. Import CSV/XLSX into metrics.db as usual
    3. Run ``--current YYYY-MM-DD --previous YYYY-MM-DD`` to see deltas
"""

from __future__ import annotations

import json
import sqlite3
import sys
from argparse import ArgumentParser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path when run directly
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from apps.control_plane.services.metrics import (
    MetricsStore,
    compute_metrics_diff,
)

_SNAPSHOT_DIR = "data/snapshots"
_SNAPSHOT_VERSION = 1

_INT_FIELDS = {
    "plays",
    "likes",
    "comments",
    "shares",
    "followers_gained",
    "exposure",
    "favorites",
    "danmaku",
    "forward_count",
}
_REAL_FIELDS = {"completion_rate", "avg_watch_duration", "cover_click_rate"}


# ── SnapshotStore ─────────────────────────────────────────────────────────────


class SnapshotStore:
    """File-based snapshot storage for incremental metric comparison.

    Snapshots are saved as ``snapshot_YYYY-MM-DD.json`` files under a
    designated directory.  Each file is a JSON array of full video_metrics
    records, wrapped with a version header for forward compatibility.
    """

    def __init__(self, snapshots_dir: str | Path = _SNAPSHOT_DIR) -> None:
        self._dir = Path(snapshots_dir)

    def path_for(self, date: str) -> Path:
        return self._dir / f"snapshot_{date}.json"

    def save(self, records: list[dict[str, Any]], date: str) -> Path:
        """Atomically write a snapshot file."""
        self._dir.mkdir(parents=True, exist_ok=True)
        dest = self.path_for(date)
        tmp = dest.with_suffix(".tmp")
        payload = {
            "version": _SNAPSHOT_VERSION,
            "snapshot_date": date,
            "records": records,
        }
        tmp.write_text(json.dumps(payload, ensure_ascii=False))
        tmp.replace(dest)
        return dest

    def load(self, date: str) -> list[dict[str, Any]]:
        """Load records from a snapshot file."""
        dest = self.path_for(date)
        if not dest.exists():
            raise FileNotFoundError(
                f"Snapshot not found: {dest}\n"
                f"Run with --save-snapshot {date} first."
            )
        payload = json.loads(dest.read_text())
        # Future-proofing — we only understand version 1 for now
        return payload["records"]

    def list_dates(self) -> list[str]:
        """Return sorted list of available snapshot dates."""
        if not self._dir.exists():
            return []
        dates: list[str] = []
        for f in sorted(self._dir.glob("snapshot_*.json")):
            date = f.stem.removeprefix("snapshot_")
            dates.append(date)
        return dates


def export_all(db_path: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        _export_overview(conn, out_dir)
        _export_videos(conn, out_dir)
        _export_topics(conn, out_dir)
    finally:
        conn.close()

    print(f"Exported to {out_dir}/")
    for f in sorted(out_dir.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name}  ({size / 1024:.1f} KB)")


# ── Row helpers ──────────────────────────────────────────────


def _row_dict(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in list(d.keys()):
        if k in _INT_FIELDS:
            d[k] = d[k] if d[k] is not None else 0
        elif k in _REAL_FIELDS:
            d[k] = d[k] if d[k] is not None else 0
        elif k in ("title", "publish_date", "platform_id", "job_id"):
            d[k] = d[k] or ""
    # Parse JSON fields
    for field in ("used_asset_ids", "extra"):
        raw = d.get(field)
        if isinstance(raw, str):
            try:
                d[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d[field] = [] if field == "used_asset_ids" else None
        elif field == "used_asset_ids" and raw is None:
            d[field] = []
    return d


def _full_row_dict(r: sqlite3.Row) -> dict:
    """Convert a row to a plain dict preserving all original values (no defaults)."""
    d = dict(r)
    for field in ("used_asset_ids", "extra"):
        raw = d.get(field)
        if isinstance(raw, str):
            try:
                d[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                d[field] = None
    return d


# ── Overview ─────────────────────────────────────────────────


def _export_overview(conn: sqlite3.Connection, out_dir: Path) -> None:
    """Write overview.json — all daily data; frontend computes range."""
    daily_rows = conn.execute(
        """SELECT
                publish_date,
                COALESCE(SUM(plays), 0)            AS plays,
                COALESCE(SUM(likes), 0)            AS likes,
                COALESCE(SUM(followers_gained), 0)  AS followers,
                COALESCE(AVG(completion_rate), 0)   AS avg_completion
            FROM video_metrics
            GROUP BY publish_date
            ORDER BY publish_date""",
    ).fetchall()

    overview = {
        "total_plays": 0,
        "total_likes": 0,
        "total_followers": 0,
        "avg_completion": 0,
        "video_count": 0,
        "daily": [dict(r) for r in daily_rows],
    }
    (out_dir / "overview.json").write_text(
        json.dumps(overview, ensure_ascii=False, indent=2)
    )


# ── Videos ───────────────────────────────────────────────────


def _export_videos(conn: sqlite3.Connection, out_dir: Path) -> None:
    """Write videos.json — all records, no pagination."""
    rows = conn.execute(
        "SELECT * FROM video_metrics ORDER BY publish_date DESC"
    ).fetchall()
    items = [_row_dict(r) for r in rows]
    (out_dir / "videos.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2)
    )


# ── Topics ───────────────────────────────────────────────────


def _export_topics(conn: sqlite3.Connection, out_dir: Path) -> None:
    """Write topics.json — top 10 keywords by total plays (last 30 days)."""
    cutoff = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")

    rows = conn.execute(
        "SELECT title, plays, completion_rate FROM video_metrics WHERE publish_date >= ?",
        (cutoff,),
    ).fetchall()

    agg: dict[str, dict] = {}
    for r in rows:
        for kw in _extract_keywords(r["title"]):
            bucket = agg.setdefault(
                kw, {"total_plays": 0, "video_count": 0, "_sum_cr": 0.0, "_count_cr": 0}
            )
            bucket["total_plays"] += r["plays"] or 0
            bucket["video_count"] += 1
            if r["completion_rate"] is not None:
                bucket["_sum_cr"] += r["completion_rate"]
                bucket["_count_cr"] += 1

    topics = []
    for kw, v in agg.items():
        avg_cr = round(v["_sum_cr"] / v["_count_cr"], 2) if v["_count_cr"] else 0.0
        topics.append(
            {
                "keyword": kw,
                "total_plays": v["total_plays"],
                "video_count": v["video_count"],
                "avg_completion": avg_cr,
            }
        )

    topics.sort(key=lambda x: x["total_plays"], reverse=True)
    (out_dir / "topics.json").write_text(
        json.dumps(topics[:10], ensure_ascii=False, indent=2)
    )


_STOPWORDS: set[str] = {
    "的",
    "了",
    "在",
    "是",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "他",
    "她",
    "它",
    "们",
    "那",
    "这个",
    "那个",
    "什么",
    "怎么",
    "可以",
    "没",
    "还",
    "把",
    "让",
    "跟",
    "从",
    "被",
    "用",
    "对",
    "做",
    "来",
    "给",
    "吗",
    "吧",
    "啊",
    "呢",
    "哦",
    "嗯",
    "啦",
    "哈",
    "呀",
    "嘛",
    "而",
    "但",
    "可是",
    "但是",
    "因为",
    "所以",
    "如果",
    "虽然",
    "不过",
    "或者",
    "还是",
    "就是",
    "已经",
    "非常",
    "比较",
    "可能",
    "而且",
    "然后",
    "其实",
    "只是",
    "真是",
    "真的",
    "一下",
    "出来",
    "起来",
    "下来",
    "上去",
    "过来",
    "过去",
}


def _extract_keywords(title: str) -> list[str]:
    import re

    tokens = re.split(r"[#，,。！？、\s]+", title.strip())
    return [t for t in tokens if len(t) >= 2 and t not in _STOPWORDS]


# ── CLI ──────────────────────────────────────────────────────


def main() -> None:
    parser = ArgumentParser(description="Export metrics.db to static JSON files")
    parser.add_argument("--db", default=None, help="Path to metrics.db (auto-detect)")
    parser.add_argument(
        "--out", default="dist", help="Output directory (default: dist/)"
    )
    parser.add_argument(
        "--save-snapshot",
        default=None,
        metavar="DATE",
        help="Save a snapshot of current DB as snapshot_DATE.json (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--current",
        default=None,
        help="Current snapshot date (YYYY-MM-DD) for increment export",
    )
    parser.add_argument(
        "--previous",
        default=None,
        help="Previous snapshot date (YYYY-MM-DD) for increment export",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)

    # Auto-detect db path
    if args.db:
        db_path = args.db
    else:
        here = Path(__file__).resolve().parent.parent
        candidates = [
            here / "data" / "metrics.db",
            here / "workspace" / "data" / "metrics.db",
        ]
        found = [p for p in candidates if p.exists()]
        if not found:
            parser.error(
                "Cannot find metrics.db. Specify --db or create data/metrics.db "
                "in the project root."
            )
        db_path = str(found[0])

    store = MetricsStore(db_path=db_path)

    # ── Save snapshot mode ──────────────────────────────────────────────
    if args.save_snapshot:
        snapshot_store = SnapshotStore()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT * FROM video_metrics").fetchall()
            records = [_full_row_dict(r) for r in rows]
        finally:
            conn.close()

        path = snapshot_store.save(records, args.save_snapshot)
        print(f"Saved snapshot: {path}  ({len(records)} records)")

        # Also run the normal export
        export_all(db_path, out_dir)
        return

    # ── Increment mode ──────────────────────────────────────────────────
    if args.current and args.previous:
        snapshot_store = SnapshotStore()

        try:
            previous_records = snapshot_store.load(args.previous)
        except FileNotFoundError as e:
            print(f"Error: {e}")
            available = snapshot_store.list_dates()
            if available:
                print(f"Available snapshots: {', '.join(available)}")
            return

        # Compute increment by comparing saved snapshot vs current DB
        increment = store.compute_increment_vs_snapshot(
            snapshot_records=previous_records,
            snapshot_date=args.current,
            previous_snapshot_date=args.previous,
            include_detail=True,
        )

        out_dir.mkdir(parents=True, exist_ok=True)

        inc_out: dict[str, Any] = {
            "snapshot_date": increment["snapshot_date"],
            "previous_snapshot": increment["previous_snapshot"],
            "summary": increment["summary"],
            "top_gainers": increment["top_gainers"],
            "daily_trend": increment["daily_trend"],
        }
        (out_dir / "increment.json").write_text(
            json.dumps(inc_out, ensure_ascii=False, indent=2)
        )

        (out_dir / "increment-detail.json").write_text(
            json.dumps(increment["detail"], ensure_ascii=False, indent=2)
        )

        print(f"Exported increment data to {out_dir}/")
        for f in sorted(out_dir.iterdir()):
            size = f.stat().st_size
            print(f"  {f.name}  ({size / 1024:.1f} KB)")
        return

    # ── Normal export mode ──────────────────────────────────────────────
    export_all(db_path, out_dir)


if __name__ == "__main__":
    main()
