import sqlite3
from pathlib import Path

_stores: dict[str, "ScheduleStore"] = {}


class ScheduleStore:
    @classmethod
    def get(cls, root_dir: Path) -> "ScheduleStore":
        key = str(root_dir.resolve())
        if key not in _stores:
            _stores[key] = cls(root_dir)
        return _stores[key]

    def __init__(self, root_dir: Path):
        db_path = root_dir / "schedule.db"
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS schedule_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        self._conn.commit()

    def add(
        self, job_id: str, platform: str, title: str = "", description: str = ""
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO schedule_entries (job_id, platform, title, description) VALUES (?, ?, ?, ?)",
            (job_id, platform, title, description),
        )
        self._conn.commit()
        assert cur.lastrowid is not None
        return cur.lastrowid

    def list(
        self, project_id: str | None = None, platform: str | None = None
    ) -> list[dict]:
        sql = "SELECT * FROM schedule_entries WHERE 1=1"
        params: list = []
        if project_id:
            sql += " AND job_id LIKE ?"
            params.append(f"%{project_id}%")
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        sql += " ORDER BY created_at DESC"
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def update_status(self, entry_id: int, status: str) -> None:
        self._conn.execute(
            "UPDATE schedule_entries SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, entry_id),
        )
        self._conn.commit()
