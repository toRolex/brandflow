"""Tests for POST /api/assets/migrate endpoint — source_videos table sync (issue #117).

Issue #118: Conflict handling enhancement and post-verification.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app


def _create_project_db(
    project_dir: Path, assets: list[dict], source_videos: list[dict]
) -> Path:
    """Create a project asset_index.db with assets and source_videos tables."""
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

    for asset in assets:
        conn.execute(
            """INSERT OR REPLACE INTO assets
               (asset_id, file_path, category, product, confidence, duration_seconds,
                status, usage_count, source_video, tags, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset["asset_id"],
                asset.get("file_path", f"/tmp/{asset['asset_id']}.mp4"),
                asset.get("category", ""),
                asset.get("product", ""),
                asset.get("confidence", 0.9),
                asset.get("duration_seconds", 5.0),
                asset.get("status", "available"),
                asset.get("usage_count", 0),
                asset.get("source_video", ""),
                asset.get("tags", "[]"),
                asset.get("created_at", datetime.now(timezone.utc).isoformat()),
                asset.get("last_used_at", ""),
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


def test_migrate_source_videos_direct_transfer(tmp_path: Path) -> None:
    """旧项目的 source_videos 表记录应直接迁移到全局 DB。"""
    # Create a project with populated source_videos table
    project_dir = tmp_path / "workspace" / "projects" / "prj_migrate"
    (project_dir / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)

    _create_project_db(
        project_dir,
        assets=[
            {
                "asset_id": "a1",
                "source_video": "/videos/cut.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
            },
            {
                "asset_id": "a2",
                "source_video": "/videos/stir.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
            },
        ],
        source_videos=[
            {"source_path": "/videos/cut.mp4"},
            {"source_path": "/videos/stir.mp4"},
        ],
    )

    with TestClient(create_app(tmp_path)) as client:
        resp = client.post("/api/assets/migrate")

        assert resp.status_code == 200
        assert resp.json()["migrated_projects"] == 1
        assert resp.json()["migrated_clips"] == 2

        # Verify source_videos table in global DB
        global_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        conn = sqlite3.connect(str(global_db))
        rows = conn.execute(
            "SELECT source_path FROM source_videos ORDER BY source_path"
        ).fetchall()
        conn.close()
        paths = [r[0] for r in rows]
        assert "/videos/cut.mp4" in paths
        assert "/videos/stir.mp4" in paths
        assert len(paths) == 2


def test_migrate_source_videos_multi_project(tmp_path: Path) -> None:
    """多个旧项目的 source_videos 应全部合并到全局 DB。"""
    now = datetime.now(timezone.utc).isoformat()

    for pid in ("prj_a", "prj_b"):
        project_dir = tmp_path / "workspace" / "projects" / pid
        (project_dir / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
        _create_project_db(
            project_dir,
            assets=[
                {
                    "asset_id": f"{pid}_a1",
                    "source_video": f"/videos/{pid}_1.mp4",
                    "category": "产品特写",
                    "product": "荔枝菌",
                    "created_at": now,
                },
            ],
            source_videos=[
                {"source_path": f"/videos/{pid}_1.mp4"},
            ],
        )

    with TestClient(create_app(tmp_path)) as client:
        resp = client.post("/api/assets/migrate")

        assert resp.status_code == 200
        assert resp.json()["migrated_projects"] == 2

        global_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        conn = sqlite3.connect(str(global_db))
        rows = conn.execute(
            "SELECT source_path FROM source_videos ORDER BY source_path"
        ).fetchall()
        conn.close()
        paths = [r[0] for r in rows]
        assert "/videos/prj_a_1.mp4" in paths
        assert "/videos/prj_b_1.mp4" in paths
        assert len(paths) == 2


def test_migrate_source_videos_backfill_conflict(tmp_path: Path) -> None:
    """因 INSERT OR IGNORE 冲突导致资产被丢弃时，其 source_video 应被回填。"""
    now = datetime.now(timezone.utc).isoformat()

    # Project A: asset "a1" pointing to /videos/cut.mp4
    prj_a = tmp_path / "workspace" / "projects" / "prj_a"
    (prj_a / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    _create_project_db(
        prj_a,
        assets=[
            {
                "asset_id": "shared_a1",
                "source_video": "/videos/cut.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            }
        ],
        source_videos=[{"source_path": "/videos/cut.mp4"}],
    )

    # Migrate project A
    with TestClient(create_app(tmp_path)) as client:
        client.post("/api/assets/migrate")

    # Now simulate Project B with SAME asset_id but DIFFERENT source_video
    prj_b = tmp_path / "workspace" / "projects" / "prj_b"
    (prj_b / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    _create_project_db(
        prj_b,
        assets=[
            {
                "asset_id": "shared_a1",  # same id — INSERT OR IGNORE will skip
                "source_video": "/videos/stir.mp4",  # different source
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            }
        ],
        source_videos=[{"source_path": "/videos/stir.mp4"}],
    )

    # Re-create app to pick up project_b (tmp_path is shared)
    with TestClient(create_app(tmp_path)) as client2:
        resp2 = client2.post("/api/assets/migrate")

        assert resp2.status_code == 200

        # Assets table should still have only one record (shared_a1 from project A)
        global_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        conn = sqlite3.connect(str(global_db))
        asset_count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        assert asset_count == 1, (
            "Only 1 asset should exist (the 2nd was INSERT OR IGNORE)"
        )

        # But source_videos should have BOTH entries
        rows = conn.execute(
            "SELECT source_path FROM source_videos ORDER BY source_path"
        ).fetchall()
        conn.close()
        paths = [r[0] for r in rows]
        assert "/videos/cut.mp4" in paths, "Project A's source_video should exist"
        assert "/videos/stir.mp4" in paths, (
            "Project B's source_video should also exist despite asset conflict"
        )
        assert len(paths) == 2


def test_migrate_source_videos_parity_with_old_project(tmp_path: Path) -> None:
    """全局 DB 的 source_videos 内容与旧项目一致。"""
    now = datetime.now(timezone.utc).isoformat()

    project_dir = tmp_path / "workspace" / "projects" / "prj_parity"
    (project_dir / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)

    old_source_videos = [
        {"source_path": "/videos/cut.mp4", "indexed_at": now},
        {"source_path": "/videos/stir.mp4", "indexed_at": now},
        {"source_path": "/videos/macro.mp4", "indexed_at": now},
    ]
    _create_project_db(
        project_dir,
        assets=[
            {
                "asset_id": "a1",
                "source_video": "/videos/cut.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
            {
                "asset_id": "a2",
                "source_video": "/videos/stir.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
        ],
        source_videos=old_source_videos,
    )

    with TestClient(create_app(tmp_path)) as client:
        client.post("/api/assets/migrate")

        global_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        conn = sqlite3.connect(str(global_db))
        rows = conn.execute(
            "SELECT source_path, indexed_at FROM source_videos ORDER BY source_path"
        ).fetchall()
        conn.close()

        migrated = {r[0]: r[1] for r in rows}
        assert len(migrated) == 3
        for sv in old_source_videos:
            assert sv["source_path"] in migrated
            assert migrated[sv["source_path"]] == sv["indexed_at"], (
                "indexed_at timestamp should be preserved"
            )


def test_migrate_source_videos_empty_old_table(tmp_path: Path) -> None:
    """旧项目 source_videos 表为空时，迁移后应有 assets.source_video 回填数据。"""
    now = datetime.now(timezone.utc).isoformat()

    project_dir = tmp_path / "workspace" / "projects" / "prj_empty"
    (project_dir / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)

    # Create project DB with assets but NO source_videos entries
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
    conn.execute(
        """INSERT INTO assets (asset_id, file_path, category, product, source_video, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("a1", "/tmp/a1.mp4", "产品特写", "荔枝菌", "/videos/cut.mp4", now),
    )
    conn.commit()
    conn.close()

    with TestClient(create_app(tmp_path)) as client:
        resp = client.post("/api/assets/migrate")

        assert resp.status_code == 200
        assert resp.json()["migrated_projects"] == 1

        global_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        conn = sqlite3.connect(str(global_db))
        rows = conn.execute("SELECT source_path FROM source_videos").fetchall()
        conn.close()
        paths = [r[0] for r in rows]
        assert "/videos/cut.mp4" in paths, (
            "source_video from assets.source_video should be backfilled"
        )


def test_migrate_source_videos_response_count(tmp_path: Path) -> None:
    """迁移响应应包含 migrated_video_source_records 计数。"""
    now = datetime.now(timezone.utc).isoformat()

    project_dir = tmp_path / "workspace" / "projects" / "prj_count"
    (project_dir / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    _create_project_db(
        project_dir,
        assets=[
            {
                "asset_id": "a1",
                "source_video": "/videos/cut.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            }
        ],
        source_videos=[{"source_path": "/videos/cut.mp4"}],
    )

    with TestClient(create_app(tmp_path)) as client:
        resp = client.post("/api/assets/migrate")

        data = resp.json()
        assert "migrated_video_source_records" in data
        assert data["migrated_video_source_records"] >= 1


def test_migrate_conflict_tracking_and_skipped_ids(tmp_path: Path) -> None:
    """冲突资产应被记录为 conflicts 和 skipped_ids 而非计入 migrated_clips。"""
    now = datetime.now(timezone.utc).isoformat()

    # Project A: 2 assets, no file needed since we only test DB
    prj_a = tmp_path / "workspace" / "projects" / "prj_a"
    (prj_a / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    _create_project_db(
        prj_a,
        assets=[
            {
                "asset_id": "shared_001",
                "source_video": "/videos/a.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
            {
                "asset_id": "shared_002",
                "source_video": "/videos/b.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
        ],
        source_videos=[],
    )

    # First migration: both succeed
    with TestClient(create_app(tmp_path)) as client:
        resp1 = client.post("/api/assets/migrate")
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["migrated_clips"] == 2
        assert data1["conflicts"] == 0
        assert data1["skipped_ids"] == []
        assert "verification" in data1

    # Project B: 1 new asset + 1 conflicting (shared_001)
    prj_b = tmp_path / "workspace" / "projects" / "prj_b"
    (prj_b / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    _create_project_db(
        prj_b,
        assets=[
            {
                "asset_id": "shared_001",  # conflict!
                "source_video": "/videos/a.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
            {
                "asset_id": "unique_003",
                "source_video": "/videos/c.mp4",
                "category": "成品展示",
                "product": "荔枝菌",
                "created_at": now,
            },
        ],
        source_videos=[],
    )

    # Second migration: prj_a re-processed (2 conflicts) + prj_b (1 conflict, 1 new)
    with TestClient(create_app(tmp_path)) as client2:
        resp2 = client2.post("/api/assets/migrate")
        assert resp2.status_code == 200
        data2 = resp2.json()

        # Only the truly new asset should count
        assert data2["migrated_clips"] == 1
        # Conflicts: prj_a 2 + prj_b 1 = 3
        assert data2["conflicts"] == 3
        assert "shared_001" in data2["skipped_ids"]
        assert "shared_002" in data2["skipped_ids"]
        assert len(data2["skipped_ids"]) == 3


def test_migrate_verification_block(tmp_path: Path) -> None:
    """迁移响应应包含 verification 块报告 old_count / new_count / diff。"""
    now = datetime.now(timezone.utc).isoformat()

    # Project: 2 assets, no conflicts expected
    prj = tmp_path / "workspace" / "projects" / "prj_verify"
    (prj / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    _create_project_db(
        prj,
        assets=[
            {
                "asset_id": "v001",
                "source_video": "/videos/a.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
            {
                "asset_id": "v002",
                "source_video": "/videos/b.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
        ],
        source_videos=[],
    )

    with TestClient(create_app(tmp_path)) as client:
        resp = client.post("/api/assets/migrate")
        assert resp.status_code == 200
        data = resp.json()

        assert "verification" in data
        v = data["verification"]
        assert "old_count" in v
        assert "new_count" in v
        assert "diff" in v

        # old_count should be total rows across all project DBs
        assert v["old_count"] == 2
        # new_count should be rows in shared DB after migration
        assert v["new_count"] == 2
        # diff = new_count - old_count
        assert v["diff"] == 0


def test_migrate_verification_shows_loss_on_conflict(tmp_path: Path) -> None:
    """冲突导致行数跳过的场景下 diff 应为负数。"""
    now = datetime.now(timezone.utc).isoformat()

    prj_a = tmp_path / "workspace" / "projects" / "prj_a"
    (prj_a / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    _create_project_db(
        prj_a,
        assets=[
            {
                "asset_id": "loss_001",
                "source_video": "/videos/a.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
        ],
        source_videos=[],
    )

    # First migration — 1 asset
    with TestClient(create_app(tmp_path)) as client:
        resp1 = client.post("/api/assets/migrate")
        assert resp1.status_code == 200
        assert resp1.json()["verification"]["diff"] == 0
        assert resp1.json()["verification"]["new_count"] == 1

    # Second project with same asset_id
    prj_b = tmp_path / "workspace" / "projects" / "prj_b"
    (prj_b / "runtime" / "source_assets").mkdir(parents=True, exist_ok=True)
    _create_project_db(
        prj_b,
        assets=[
            {
                "asset_id": "loss_001",  # conflict
                "source_video": "/videos/b.mp4",
                "category": "产品特写",
                "product": "荔枝菌",
                "created_at": now,
            },
        ],
        source_videos=[],
    )

    # Second migration: prj_a re-processed (1 conflict) + prj_b (1 conflict) = 2 conflicts
    with TestClient(create_app(tmp_path)) as client2:
        resp2 = client2.post("/api/assets/migrate")
        assert resp2.status_code == 200
        data2 = resp2.json()
        # migrated_clips = 0 (nothing new)
        assert data2["migrated_clips"] == 0
        # old_count = 2 (prj_a has 1, prj_b has 1)
        assert data2["verification"]["old_count"] == 2
        # new_count = 1 (still only loss_001)
        assert data2["verification"]["new_count"] == 1
        # diff = 1 - 2 = -1
        assert data2["verification"]["diff"] == -1


def test_migrate_no_conflicts_no_verification_fields_defaults(tmp_path: Path) -> None:
    """无项目时新字段应返回合理默认值。"""
    # No projects at all
    with TestClient(create_app(tmp_path)) as client:
        resp = client.post("/api/assets/migrate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["conflicts"] == 0
        assert data["skipped_ids"] == []
        assert "verification" in data
        assert data["verification"]["old_count"] == 0
        assert data["verification"]["new_count"] == 0
        assert data["verification"]["diff"] == 0
