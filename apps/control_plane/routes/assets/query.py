"""Indexed asset query endpoint."""

from __future__ import annotations

import json
import sqlite3

from pathlib import Path

from fastapi import APIRouter, Query, Request

from packages.pagination import DEFAULT_PAGE_SIZE

router = APIRouter()

DEFAULT_PAGE = 1


@router.get("/indexed")
def get_indexed_assets(
    request: Request,
    category: str | None = Query(default=None),
    q: str | None = Query(default=None),
    product: str | None = Query(default=None),
    status: str | None = Query(default=None),
    duration_min: float | None = Query(default=None),
    duration_max: float | None = Query(default=None),
    confidence_min: float | None = Query(default=None),
    confidence_max: float | None = Query(default=None),
    usage_min: int | None = Query(default=None),
    usage_max: int | None = Query(default=None),
    page: int = Query(default=DEFAULT_PAGE, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
):
    root_dir: Path = request.app.state.root_dir
    db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    if not db_path.exists():
        return {
            "assets": [],
            "stats": {
                "total_clips": 0,
                "available_clips": 0,
                "disabled_clips": 0,
                "source_videos": 0,
                "category_counts": {},
                "duration_min": 0,
                "duration_max": 0,
                "usage_min": 0,
                "usage_max": 0,
            },
            "page": page,
            "page_size": page_size,
            "total": 0,
        }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        base_query = "SELECT * FROM assets"
        count_query = "SELECT COUNT(*) FROM assets"
        conditions: list[str] = []
        params: list[object] = []

        def add_condition(sql: str, value: object) -> None:
            conditions.append(sql)
            params.append(value)

        if category:
            add_condition("category = ?", category)
        if q:
            conditions.append(
                "(file_path LIKE ? OR source_video LIKE ? OR tags LIKE ?)"
            )
            like_q = f"%{q}%"
            params.extend([like_q, like_q, like_q])
        if product:
            add_condition("product = ?", product)
        if status:
            add_condition("status = ?", status)
        if duration_min is not None:
            add_condition("duration_seconds >= ?", duration_min)
        if duration_max is not None and duration_max > 0:
            add_condition("duration_seconds <= ?", duration_max)
        if confidence_min is not None:
            add_condition("confidence >= ?", confidence_min)
        if confidence_max is not None and confidence_max > 0:
            add_condition("confidence <= ?", confidence_max)
        if usage_min is not None:
            add_condition("usage_count >= ?", usage_min)
        if usage_max is not None and usage_max > 0:
            add_condition("usage_count <= ?", usage_max)

        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        base_query += where_clause
        count_query += where_clause

        total = conn.execute(count_query, params).fetchone()[0]

        base_query += " ORDER BY created_at DESC"
        base_query += " LIMIT ? OFFSET ?"
        query_params = list(params) + [page_size, (page - 1) * page_size]

        rows = conn.execute(base_query, query_params).fetchall()

        # Aggregate stats over the full filtered result set, not just the page.
        stats_query = (
            """
            SELECT
                COALESCE(SUM(status = 'available'), 0) AS available_clips,
                COALESCE(SUM(status = 'disabled'), 0) AS disabled_clips,
                COUNT(DISTINCT NULLIF(source_video, '')) AS source_videos,
                COALESCE(MIN(duration_seconds), 0) AS duration_min,
                COALESCE(MAX(duration_seconds), 0) AS duration_max,
                COALESCE(MIN(usage_count), 0) AS usage_min,
                COALESCE(MAX(usage_count), 0) AS usage_max
            FROM assets
        """
            + where_clause
        )
        stats_row = conn.execute(stats_query, params).fetchone()

        # Category counts ignore the category filter so the dropdown stays useful.
        facet_conditions = [c for c in conditions if not c.startswith("category =")]
        facet_where = (
            " WHERE " + " AND ".join(facet_conditions) if facet_conditions else ""
        )
        facet_query = (
            "SELECT category, COUNT(*) AS n FROM assets"
            + facet_where
            + " GROUP BY category"
        )
        # Params for facet query exclude the category value if it was filtered.
        facet_params: list[object] = []
        if category:
            facet_params = params[:-1]
        else:
            facet_params = list(params)
        category_counts = {
            row["category"]: row["n"]
            for row in conn.execute(facet_query, facet_params).fetchall()
        }

        assets = []
        for row in rows:
            d = dict(row)
            raw_tags = d.get("tags")
            if isinstance(raw_tags, str):
                try:
                    d["tags"] = json.loads(raw_tags)
                except (json.JSONDecodeError, TypeError):
                    d["tags"] = []
            assets.append(d)

        return {
            "assets": assets,
            "stats": {
                "total_clips": total,
                "available_clips": stats_row["available_clips"],
                "disabled_clips": stats_row["disabled_clips"],
                "source_videos": stats_row["source_videos"],
                "category_counts": category_counts,
                "duration_min": stats_row["duration_min"],
                "duration_max": stats_row["duration_max"],
                "usage_min": stats_row["usage_min"],
                "usage_max": stats_row["usage_max"],
            },
            "page": page,
            "page_size": page_size,
            "total": total,
        }
    finally:
        conn.close()
