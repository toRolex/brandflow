"""Project asset migration endpoint."""

from __future__ import annotations

import json
import sqlite3
import shutil

from pathlib import Path

from fastapi import APIRouter, Request

from packages.pipeline_services.asset_library import AssetRepository

router = APIRouter()


@router.post("/migrate")
def migrate_project_assets(request: Request):
    """Migrate all per-project assets into the shared library."""
    root_dir: Path = request.app.state.root_dir
    projects_root = root_dir / "workspace" / "projects"
    if not projects_root.exists():
        return {
            "migrated_projects": 0,
            "migrated_clips": 0,
            "migrated_sources": 0,
            "migrated_video_source_records": 0,
            "conflicts": 0,
            "skipped_ids": [],
            "verification": {"old_count": 0, "new_count": 0, "diff": 0},
        }

    shared_db_path = root_dir / "workspace" / "shared_assets" / "asset_index.db"
    shared_src = root_dir / "workspace" / "shared_assets" / "source"
    shared_idx = root_dir / "workspace" / "shared_assets" / "indexed"
    shared_src.mkdir(parents=True, exist_ok=True)
    shared_idx.mkdir(parents=True, exist_ok=True)

    # Ensure shared DB table exists
    AssetRepository(shared_db_path)

    migrated_projects = 0
    migrated_clips = 0
    migrated_sources = 0
    migrated_video_source_records = 0
    conflicts = 0
    skipped_ids: list[str] = []

    # Count old DB rows before migration (for post-verification comparison)
    old_count = 0
    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir():
            continue
        old_db = project_dir / "asset_index.db"
        if old_db.exists():
            try:
                old_conn = sqlite3.connect(str(old_db))
                old_count += old_conn.execute("SELECT COUNT(*) FROM assets").fetchone()[
                    0
                ]
                old_conn.close()
            except sqlite3.Error:
                pass  # silently skip corrupt DBs

    for project_dir in sorted(projects_root.iterdir()):
        if not project_dir.is_dir():
            continue

        # Migrate source assets
        src_dir = project_dir / "runtime" / "source_assets"
        if src_dir.exists():
            for f in src_dir.iterdir():
                if f.is_file():
                    dest = shared_src / f.name
                    if not dest.exists():
                        shutil.copy2(str(f), str(dest))
                        migrated_sources += 1

        # Migrate indexed clips DB
        old_db = project_dir / "asset_index.db"
        if old_db.exists():
            old_conn = sqlite3.connect(str(old_db))
            old_conn.row_factory = sqlite3.Row
            rows = old_conn.execute("SELECT * FROM assets").fetchall()

            # Migrate source_videos table from old DB
            old_source_rows = old_conn.execute(
                "SELECT source_path, indexed_at FROM source_videos"
            ).fetchall()
            if old_source_rows:
                new_conn = sqlite3.connect(str(shared_db_path))
                for source_path, indexed_at in old_source_rows:
                    new_conn.execute(
                        "INSERT OR IGNORE INTO source_videos (source_path, indexed_at) VALUES (?, ?)",
                        (source_path, indexed_at),
                    )
                new_conn.commit()
                new_conn.close()
                migrated_video_source_records += len(old_source_rows)

            old_conn.close()

            if rows:
                new_conn = sqlite3.connect(str(shared_db_path))
                for row in rows:
                    d = dict(row)
                    # Rewrite file_path from per-project dir to shared_assets/indexed
                    old_fp = Path(d["file_path"])
                    d["file_path"] = str(
                        shared_idx / d["product"] / d["category"] / old_fp.name
                    )
                    cursor = new_conn.execute(
                        """INSERT OR IGNORE INTO assets
                           (asset_id, file_path, category, product, confidence, duration_seconds,
                            status, usage_count, source_video, tags, created_at, last_used_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            d["asset_id"],
                            d["file_path"],
                            d["category"],
                            d["product"],
                            d["confidence"],
                            d["duration_seconds"],
                            d["status"],
                            d["usage_count"],
                            d["source_video"],
                            d["tags"]
                            if isinstance(d["tags"], str)
                            else json.dumps(d["tags"], ensure_ascii=False),
                            d["created_at"],
                            d["last_used_at"],
                        ),
                    )
                    if cursor.rowcount > 0:
                        migrated_clips += 1
                    else:
                        conflicts += 1
                        skipped_ids.append(d["asset_id"])
                new_conn.commit()
                new_conn.close()
                migrated_projects += 1

        # Migrate indexed clips files
        idx_dir = project_dir / "runtime" / "indexed_clips"
        if idx_dir.exists():
            for product_dir in idx_dir.iterdir():
                if not product_dir.is_dir():
                    continue
                for cat_dir in product_dir.iterdir():
                    if not cat_dir.is_dir():
                        continue
                    dest_cat = shared_idx / product_dir.name / cat_dir.name
                    dest_cat.mkdir(parents=True, exist_ok=True)
                    for clip in cat_dir.iterdir():
                        if clip.is_file():
                            dest = dest_cat / clip.name
                            if not dest.exists():
                                shutil.copy2(str(clip), str(dest))

    # Backfill any source_video references from assets that were added
    # via INSERT OR IGNORE conflicts
    repo = AssetRepository(shared_db_path)
    backfilled = repo.backfill_source_videos()
    migrated_video_source_records += backfilled

    # Post-verification: count rows in shared DB after migration
    new_count = 0
    shared_db = Path(shared_db_path)
    if shared_db.exists():
        try:
            verify_conn = sqlite3.connect(str(shared_db))
            new_count = verify_conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
            verify_conn.close()
        except sqlite3.Error:
            pass

    return {
        "migrated_projects": migrated_projects,
        "migrated_clips": migrated_clips,
        "migrated_sources": migrated_sources,
        "migrated_video_source_records": migrated_video_source_records,
        "conflicts": conflicts,
        "skipped_ids": skipped_ids,
        "verification": {
            "old_count": old_count,
            "new_count": new_count,
            "diff": new_count - old_count,
        },
    }
