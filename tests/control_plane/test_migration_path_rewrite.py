"""Tests for POST /api/assets/migrate — file_path rewrite to shared_assets.

Issue #116: After migration, assets.file_path must point to
workspace/shared_assets/indexed/{product}/{category}/{filename}
instead of the old per-project path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from packages.pipeline_services.asset_library import (
    AssetRecord,
    AssetRepository,
)


def _make_client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path))


def _create_project_with_assets(
    root_dir: Path,
    project_id: str = "prj_migrate",
    product: str = "荔枝菌",
    category: str = "产品特写",
    asset_id: str | None = None,
) -> tuple[Path, str]:
    """Create a per-project directory with an old asset_index.db + indexed clip file.

    Returns (old_db_path, old_file_path_as_string).
    """
    actual_asset_id = asset_id or f"asset_{project_id}"
    project_dir = root_dir / "workspace" / "projects" / project_id

    # Old indexed clips directory structure (as created by per-project indexing)
    indexed_dir = project_dir / "runtime" / "indexed_clips" / product / category
    indexed_dir.mkdir(parents=True, exist_ok=True)
    clip_file = indexed_dir / f"{project_id}_clip_001.mp4"
    clip_file.write_bytes(b"fake clip content for migration test")

    # Old project-level asset_index.db
    old_db = project_dir / "asset_index.db"
    repo = AssetRepository(old_db)
    old_file_path = str(clip_file.resolve())
    repo.insert(
        AssetRecord(
            asset_id=actual_asset_id,
            file_path=old_file_path,
            category=category,
            product=product,
            duration_seconds=5.0,
            status="available",
        )
    )
    return old_db, old_file_path


# ── file_path rewrite ──


def test_migrate_rewrites_file_path_to_shared_assets(tmp_path: Path) -> None:
    """After migration, assets.file_path must point to shared_assets/indexed."""
    with _make_client(tmp_path) as client:
        old_db, old_file_path = _create_project_with_assets(
            tmp_path, asset_id="asset_mig_001"
        )

        resp = client.post("/api/assets/migrate")
        assert resp.status_code == 200
        result = resp.json()
        assert result["migrated_projects"] >= 1
        assert result["migrated_clips"] >= 1

        # Verify shared DB
        shared_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        assert shared_db.exists()

        conn = sqlite3.connect(str(shared_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path, product, category FROM assets WHERE asset_id = ?",
            ("asset_mig_001",),
        ).fetchone()
        conn.close()

        assert row is not None, "migrated asset should exist in shared DB"
        new_file_path = row["file_path"]

        # file_path should NOT point to old per-project path
        assert "projects/" not in new_file_path, (
            f"file_path should not contain 'projects/', got: {new_file_path}"
        )
        # file_path SHOULD point to shared_assets/indexed
        assert "shared_assets/indexed" in new_file_path, (
            f"file_path should contain 'shared_assets/indexed', got: {new_file_path}"
        )
        # Verify product/category in path
        assert row["product"] in new_file_path
        assert row["category"] in new_file_path

        # Verify the file exists at the new path
        new_path = Path(new_file_path)
        assert new_path.exists(), f"file should exist at new path: {new_file_path}"

        # Verify the file content is intact
        assert new_path.read_bytes() == b"fake clip content for migration test"


def test_migrate_rewrite_multiple_products(tmp_path: Path) -> None:
    """Migration rewrites file_path for multiple products correctly."""
    with _make_client(tmp_path) as client:
        _create_project_with_assets(
            tmp_path,
            "prj_a",
            product="荔枝菌",
            category="成品展示",
            asset_id="asset_prj_a",
        )
        _create_project_with_assets(
            tmp_path,
            "prj_b",
            product="羊肚菌",
            category="产品特写",
            asset_id="asset_prj_b",
        )

        resp = client.post("/api/assets/migrate")
        assert resp.status_code == 200
        assert resp.json()["migrated_clips"] >= 2

        shared_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        conn = sqlite3.connect(str(shared_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT asset_id, file_path, product, category FROM assets ORDER BY asset_id"
        ).fetchall()
        conn.close()

        assert len(rows) == 2

        for row in rows:
            fp = row["file_path"]
            assert "shared_assets/indexed" in fp
            assert row["product"] in fp
            assert row["category"] in fp
            assert Path(fp).exists(), f"file should exist at {fp}"


def test_migrate_skip_when_asset_id_already_exists(tmp_path: Path) -> None:
    """Re-running migration should skip already-migrated records (INSERT OR IGNORE)."""
    with _make_client(tmp_path) as client:
        old_db, old_file_path = _create_project_with_assets(
            tmp_path, asset_id="asset_mig_002"
        )

        # First migration
        resp1 = client.post("/api/assets/migrate")
        assert resp1.status_code == 200

        # Verify the file_path was rewritten after first migration
        shared_db = tmp_path / "workspace" / "shared_assets" / "asset_index.db"
        conn = sqlite3.connect(str(shared_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path FROM assets WHERE asset_id = ?", ("asset_mig_002",)
        ).fetchone()
        conn.close()
        assert row is not None
        correct_path = row["file_path"]

        # Second migration should not error and should not duplicate
        resp2 = client.post("/api/assets/migrate")
        assert resp2.status_code == 200

        conn2 = sqlite3.connect(str(shared_db))
        count = conn2.execute(
            "SELECT COUNT(*) FROM assets WHERE asset_id = ?", ("asset_mig_002",)
        ).fetchone()[0]
        file_path = conn2.execute(
            "SELECT file_path FROM assets WHERE asset_id = ?", ("asset_mig_002",)
        ).fetchone()[0]
        conn2.close()

        assert count == 1, "should not duplicate asset records"
        assert file_path == correct_path, (
            "file_path should remain unchanged on re-migration"
        )
