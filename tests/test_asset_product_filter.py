"""Tests for product filtering in asset API endpoints."""

import sqlite3
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from apps.control_plane.app import create_app


def _build_app_with_asset_db(root_dir: Path, assets: list[dict]):
    """Create a FastAPI test app with a pre-populated shared asset DB."""
    shared_dir = root_dir / "workspace" / "shared_assets"
    shared_dir.mkdir(parents=True, exist_ok=True)
    db_path = shared_dir / "asset_index.db"

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            file_path TEXT,
            category TEXT,
            product TEXT,
            confidence REAL,
            duration_seconds REAL,
            status TEXT,
            usage_count INTEGER,
            source_video TEXT,
            tags TEXT,
            created_at TEXT,
            last_used_at TEXT
        )"""
    )
    for a in assets:
        conn.execute(
            """INSERT OR REPLACE INTO assets
               (asset_id, file_path, category, product, confidence, duration_seconds,
                status, usage_count, source_video, tags, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                a["asset_id"],
                a["file_path"],
                a.get("category", ""),
                a.get("product", ""),
                a.get("confidence", 0.9),
                a.get("duration_seconds", 5.0),
                a.get("status", "available"),
                a.get("usage_count", 0),
                a.get("source_video", ""),
                a.get("tags", "[]"),
                a.get("created_at", "2025-01-01T00:00:00"),
                a.get("last_used_at", "2025-01-01T00:00:00"),
            ),
        )
    conn.commit()
    conn.close()

    return create_app(root_dir=root_dir)


def test_indexed_assets_filters_by_product():
    """GET /api/assets/indexed?product=X returns only assets matching product."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        assets = [
            {
                "asset_id": "a1",
                "file_path": "/tmp/a1.mp4",
                "product": "龙井茶",
                "category": "冲泡",
            },
            {
                "asset_id": "a2",
                "file_path": "/tmp/a2.mp4",
                "product": "龙井茶",
                "category": "产地",
            },
            {
                "asset_id": "a3",
                "file_path": "/tmp/a3.mp4",
                "product": "普洱茶",
                "category": "冲泡",
            },
        ]
        app = _build_app_with_asset_db(root, assets)
        with TestClient(app) as client:
            # Filter by product (use params to properly encode Chinese characters)
            resp = client.get("/api/assets/indexed", params={"product": "龙井茶"})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["assets"]) == 2
            returned_ids = {a["asset_id"] for a in data["assets"]}
            assert returned_ids == {"a1", "a2"}

            # Filter by other product
            resp2 = client.get("/api/assets/indexed", params={"product": "普洱茶"})
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert len(data2["assets"]) == 1
            assert data2["assets"][0]["asset_id"] == "a3"

            # No product filter returns all
            resp3 = client.get("/api/assets/indexed")
            assert resp3.status_code == 200
            data3 = resp3.json()
            assert len(data3["assets"]) == 3


def test_indexed_assets_product_and_category_combined():
    """Product and category filters combine with AND logic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        assets = [
            {
                "asset_id": "a1",
                "file_path": "/tmp/a1.mp4",
                "product": "龙井茶",
                "category": "冲泡",
            },
            {
                "asset_id": "a2",
                "file_path": "/tmp/a2.mp4",
                "product": "龙井茶",
                "category": "产地",
            },
            {
                "asset_id": "a3",
                "file_path": "/tmp/a3.mp4",
                "product": "普洱茶",
                "category": "冲泡",
            },
        ]
        app = _build_app_with_asset_db(root, assets)
        with TestClient(app) as client:
            resp = client.get(
                "/api/assets/indexed", params={"product": "龙井茶", "category": "冲泡"}
            )
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["assets"]) == 1
            assert data["assets"][0]["asset_id"] == "a1"


def test_indexed_assets_product_no_match_returns_empty():
    """Requesting a product with no assets returns empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        assets = [
            {
                "asset_id": "a1",
                "file_path": "/tmp/a1.mp4",
                "product": "龙井茶",
                "category": "冲泡",
            },
        ]
        app = _build_app_with_asset_db(root, assets)
        with TestClient(app) as client:
            resp = client.get("/api/assets/indexed", params={"product": "铁观音"})
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["assets"]) == 0
            assert data["stats"]["total_clips"] == 0
