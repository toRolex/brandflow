from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from packages.pipeline_services.asset_library.models import (
    AssetRecord,
    AssetStatus,
    Category,
)


class AssetRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        db_path_str = str(self.db_path)
        conn = sqlite3.connect(db_path_str)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                category TEXT NOT NULL,
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_category ON assets(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_product ON assets(product)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON assets(status)")

        existing_sources = conn.execute(
            "SELECT COUNT(*) FROM source_videos"
        ).fetchone()[0]
        if existing_sources == 0:
            rows = conn.execute(
                "SELECT DISTINCT source_video FROM assets WHERE source_video != ''"
            ).fetchall()
            now = datetime.now(timezone.utc).isoformat()
            for row in rows:
                conn.execute(
                    "INSERT OR IGNORE INTO source_videos (source_path, indexed_at) VALUES (?, ?)",
                    (row[0], now),
                )

        conn.commit()
        conn.close()

    def insert(self, record: AssetRecord) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if not record.created_at:
            record.created_at = now
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """INSERT OR REPLACE INTO assets
               (asset_id, file_path, category, product, confidence, duration_seconds,
                status, usage_count, source_video, tags, created_at, last_used_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.asset_id,
                record.file_path,
                record.category.value,
                record.product,
                record.confidence,
                record.duration_seconds,
                record.status,
                record.usage_count,
                record.source_video,
                json.dumps(record.tags, ensure_ascii=False),
                record.created_at,
                record.last_used_at,
            ),
        )
        conn.commit()
        conn.close()

    def query_one(self, asset_id: str) -> AssetRecord | None:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        conn.close()
        return _row_to_record(row) if row else None

    def query_by_category(self, product: str, category: Category) -> list[AssetRecord]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM assets WHERE product = ? AND category = ? AND status != 'disabled' ORDER BY usage_count ASC, confidence DESC",
            (product, category.value),
        ).fetchall()
        conn.close()
        return [_row_to_record(r) for r in rows]

    def query_by_category_name(
        self, product: str, category_name: str
    ) -> list[AssetRecord]:
        """Query assets by product and category name string.

        This is the preferred query method for configurable (non-enum) categories.
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM assets WHERE product = ? AND category = ? AND status != 'disabled' ORDER BY usage_count ASC, confidence DESC",
            (product, category_name),
        ).fetchall()
        conn.close()
        return [_row_to_record(r) for r in rows]

    def query_all_available(self, product: str) -> list[AssetRecord]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM assets WHERE product = ? AND status != 'disabled' ORDER BY usage_count ASC",
            (product,),
        ).fetchall()
        conn.close()
        return [_row_to_record(r) for r in rows]

    def get_usage_count(self, asset_id: str) -> int:
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT usage_count FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0

    def increment_usage(self, asset_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "UPDATE assets SET usage_count = usage_count + 1, last_used_at = ? WHERE asset_id = ?",
            (now, asset_id),
        )
        conn.commit()
        conn.close()

    def decrement_usage(self, asset_id: str) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "UPDATE assets SET usage_count = MAX(0, usage_count - 1) WHERE asset_id = ?",
            (asset_id,),
        )
        conn.commit()
        conn.close()

    def update_status(self, asset_id: str, status: AssetStatus) -> None:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "UPDATE assets SET status = ? WHERE asset_id = ?", (status, asset_id)
        )
        conn.commit()
        conn.close()

    def update_fields(self, asset_id: str, **kwargs) -> bool:
        allowed = {"product", "category", "status", "tags"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        if "category" in updates and isinstance(updates["category"], Category):
            updates["category"] = updates["category"].value
        if "tags" in updates and isinstance(updates["tags"], list):
            updates["tags"] = json.dumps(updates["tags"], ensure_ascii=False)
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [asset_id]
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            f"UPDATE assets SET {set_clause} WHERE asset_id = ?", values
        )
        conn.commit()
        conn.close()
        return cursor.rowcount > 0

    def count_by_category(self, product: str, category: Category) -> int:
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT COUNT(*) FROM assets WHERE product = ? AND category = ? AND status != 'disabled'",
            (product, category.value),
        ).fetchone()
        conn.close()
        return row[0] if row else 0

    def remove_by_source(self, source_video: str) -> int:
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.execute(
            "DELETE FROM assets WHERE source_video = ?", (source_video,)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    def mark_source_indexed(self, source_path: str) -> None:
        """Record that a source video has been indexed (prevents re-indexing after clip deletion)."""
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT OR REPLACE INTO source_videos (source_path, indexed_at) VALUES (?, ?)",
            (source_path, now),
        )
        conn.commit()
        conn.close()

    def get_indexed_source_paths(self) -> set[str]:
        """Return all source video paths that have been indexed at least once."""
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT source_path FROM source_videos").fetchall()
        conn.close()
        return {row[0] for row in rows}

    def remove_source_record(self, source_path: str) -> None:
        """Remove a source video from the indexed-sources tracker (e.g., when source file is deleted)."""
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM source_videos WHERE source_path = ?", (source_path,))
        conn.commit()
        conn.close()

    def count_by_source(self, source_path: str) -> int:
        """Count how many assets reference a given source video."""
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT COUNT(*) FROM assets WHERE source_video = ?", (source_path,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0

    def close(self) -> None:
        pass


def _row_to_record(row: sqlite3.Row) -> AssetRecord:
    raw_category = row["category"]
    try:
        category = Category(raw_category)
    except ValueError:
        # Config-based category name that is not in the legacy enum
        category = Category.MACRO  # fallback
    return AssetRecord(
        asset_id=row["asset_id"],
        file_path=row["file_path"],
        category=category,
        product=row["product"],
        confidence=row["confidence"],
        duration_seconds=row["duration_seconds"],
        status=row["status"],
        usage_count=row["usage_count"],
        source_video=row["source_video"],
        tags=json.loads(row["tags"]) if row["tags"] else [],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
    )
