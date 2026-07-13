"""E2E integration tests for POST /api/assets/migrate (Issue #119).

Tests the full migration flow: per-project assets + source_videos are migrated
into the global shared_assets DB, file paths are rewritten, and record counts
match expectations across the two old projects.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _create_project_db(
    project_dir: Path,
    project_id: str,
    assets: list[dict],
    source_videos: list[dict],
) -> Path:
    """Create a per-project asset_index.db with assets and source_videos tables."""
    db_path = project_dir / "asset_index.db"
    conn = sqlite3.connect(str(db_path))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            asset_id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            product TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.0,
            duration_seconds REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'available',
            usage_count INTEGER NOT NULL DEFAULT 0,
            source_video TEXT NOT NULL DEFAULT '',
            tags TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT '',
            last_used_at TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_videos (
            source_path TEXT PRIMARY KEY,
            indexed_at TEXT NOT NULL DEFAULT ''
        )
    """)

    for a in assets:
        conn.execute(
            """INSERT OR REPLACE INTO assets
               (asset_id, file_path, category, product, confidence, duration_seconds,
                status, usage_count, source_video, tags, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                a["asset_id"],
                a.get("file_path", f"/tmp/original/{project_id}/{a['asset_id']}.mp4"),
                a.get("category", ""),
                a.get("product", ""),
                a.get("confidence", 0.9),
                a.get("duration_seconds", 5.0),
                a.get("status", "available"),
                a.get("usage_count", 0),
                a.get("source_video", ""),
                a.get("tags", "[]"),
                a.get("created_at", datetime.now(timezone.utc).isoformat()),
                a.get("last_used_at", ""),
            ),
        )

    for sv in source_videos:
        conn.execute(
            "INSERT OR IGNORE INTO source_videos (source_path, indexed_at) VALUES (?, ?)",
            (
                sv["source_path"],
                sv.get("indexed_at", datetime.now(timezone.utc).isoformat()),
            ),
        )

    conn.commit()
    conn.close()
    return db_path


def _create_old_clip_file(
    project_dir: Path, product: str, category: str, filename: str
) -> Path:
    """Create a fake indexed clip file at the old per-project path and return its path."""
    clip_dir = project_dir / "runtime" / "indexed_clips" / product / category
    clip_dir.mkdir(parents=True, exist_ok=True)
    clip_file = clip_dir / filename
    clip_file.write_bytes(b"fake clip content for migration e2e test")
    return clip_file


def test_migration_e2e_two_projects(tmp_path: Path) -> None:
    """创建 2 个项目，迁移后全局 DB 记录数 = 两项目合计，file_path 重写，source_videos 完整迁移。"""
    now = datetime.now(timezone.utc).isoformat()

    # ── Project A: 2 assets, 2 source_videos ──
    prj_a = tmp_path / "workspace" / "projects" / "prj_a"
    prj_a.mkdir(parents=True, exist_ok=True)
    clip_a1 = _create_old_clip_file(prj_a, "荔枝菌", "产品特写", "clip_a1.mp4")
    clip_a2 = _create_old_clip_file(prj_a, "荔枝菌", "成品展示", "clip_a2.mp4")

    _create_project_db(
        prj_a,
        "prj_a",
        assets=[
            {
                "asset_id": "a001",
                "file_path": str(clip_a1),
                "product": "荔枝菌",
                "category": "产品特写",
                "source_video": "/videos/a_raw.mp4",
                "created_at": now,
            },
            {
                "asset_id": "a002",
                "file_path": str(clip_a2),
                "product": "荔枝菌",
                "category": "成品展示",
                "source_video": "/videos/a_raw2.mp4",
                "created_at": now,
            },
        ],
        source_videos=[
            {"source_path": "/videos/a_raw.mp4", "indexed_at": now},
            {"source_path": "/videos/a_raw2.mp4", "indexed_at": now},
        ],
    )

    # ── Project B: 3 assets, 2 source_videos (1 overlap with A) ──
    prj_b = tmp_path / "workspace" / "projects" / "prj_b"
    prj_b.mkdir(parents=True, exist_ok=True)
    clip_b1 = _create_old_clip_file(prj_b, "羊肚菌", "产品特写", "clip_b1.mp4")
    clip_b2 = _create_old_clip_file(prj_b, "羊肚菌", "产地", "clip_b2.mp4")
    clip_b3 = _create_old_clip_file(prj_b, "荔枝菌", "产品特写", "clip_b3.mp4")

    _create_project_db(
        prj_b,
        "prj_b",
        assets=[
            {
                "asset_id": "b001",
                "file_path": str(clip_b1),
                "product": "羊肚菌",
                "category": "产品特写",
                "source_video": "/videos/b_raw.mp4",
                "created_at": now,
            },
            {
                "asset_id": "b002",
                "file_path": str(clip_b2),
                "product": "羊肚菌",
                "category": "产地",
                "source_video": "/videos/b_raw.mp4",
                "created_at": now,
            },
            {
                "asset_id": "b003",
                "file_path": str(clip_b3),
                "product": "荔枝菌",
                "category": "产品特写",
                "source_video": "/videos/b_raw3.mp4",
                "created_at": now,
            },
        ],
        source_videos=[
            {"source_path": "/videos/b_raw.mp4", "indexed_at": now},
            {"source_path": "/videos/b_raw3.mp4", "indexed_at": now},
        ],
    )

    # ── Act: migrate ──
    client = TestClient(create_app(tmp_path))
    resp = client.post("/api/assets/migrate")

    # ── Assert response ──
    assert resp.status_code == 200
    data = resp.json()
    assert data["migrated_projects"] == 2
    # 2 (prj_a) + 3 (prj_b) = 5
    assert data["migrated_clips"] == 5, (
        f"Expected 5 migrated clips, got {data['migrated_clips']}"
    )
    # source_videos: 2 (prj_a) + 2 (prj_b) = 4
    assert data["migrated_video_source_records"] == 4, (
        f"Expected 4 migrated source video records, got {data['migrated_video_source_records']}"
    )

    # ── Verify global DB total record count = 5 ──
    global_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
    assert global_db.exists(), "shared asset_index.db should exist after migration"

    conn = sqlite3.connect(str(global_db))
    conn.row_factory = sqlite3.Row

    try:
        total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        assert total == 5, f"Expected 5 assets in global DB, got {total}"

        # ── Verify file_path rewritten to shared_assets/indexed/{product}/{category}/{filename} ──
        rows = conn.execute(
            "SELECT asset_id, file_path, product, category FROM assets ORDER BY asset_id"
        ).fetchall()

        for row in rows:
            fp = row["file_path"]
            assert "shared_assets/indexed" in fp, (
                f"file_path '{fp}' should contain 'shared_assets/indexed'"
            )
            assert "projects/" not in fp, (
                f"file_path '{fp}' should not contain 'projects/'"
            )
            assert row["product"] in fp, (
                f"file_path '{fp}' should contain product '{row['product']}'"
            )
            assert row["category"] in fp, (
                f"file_path '{fp}' should contain category '{row['category']}'"
            )
            # Verify the clip file exists at the new path
            assert Path(fp).exists(), f"file should exist at new path: {fp}"

        # ── Verify source_videos complete migration ──
        sv_rows = conn.execute(
            "SELECT source_path FROM source_videos ORDER BY source_path"
        ).fetchall()
        sv_paths = [r["source_path"] for r in sv_rows]

        expected_sv = {
            "/videos/a_raw.mp4",
            "/videos/a_raw2.mp4",
            "/videos/b_raw.mp4",
            "/videos/b_raw3.mp4",
        }
        assert len(sv_paths) == 4, (
            f"Expected 4 source_video records, got {len(sv_paths)}"
        )
        for path in expected_sv:
            assert path in sv_paths, (
                f"Expected source_video '{path}' to exist in global DB"
            )

        # ── Verify specific asset data integrity ──
        a001 = conn.execute(
            "SELECT asset_id, product, category, source_video FROM assets WHERE asset_id = ?",
            ("a001",),
        ).fetchone()
        assert a001 is not None
        assert a001["product"] == "荔枝菌"
        assert a001["category"] == "产品特写"
        assert a001["source_video"] == "/videos/a_raw.mp4"

        b002 = conn.execute(
            "SELECT asset_id, product, category, source_video FROM assets WHERE asset_id = ?",
            ("b002",),
        ).fetchone()
        assert b002 is not None
        assert b002["product"] == "羊肚菌"
        assert b002["category"] == "产地"
        assert b002["source_video"] == "/videos/b_raw.mp4"

    finally:
        conn.close()
