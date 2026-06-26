"""Tests for MetricsStore — CSV (微信视频号) and XLSX (小红书) import."""
import csv
import io
import sqlite3
import tempfile
from pathlib import Path

import pytest
from openpyxl import Workbook

from apps.control_plane.services.metrics import MetricsStore


@pytest.fixture
def store(tmp_path):
    return MetricsStore(db_path=str(tmp_path / "test_metrics.db"))


def _write_csv(rows: list[list[str]]) -> bytes:
    """Build a UTF-8-BOM CSV payload."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _write_xlsx(rows: list[list], path: Path) -> Path:
    """Build a minimal xlsx file matching 小红书 export format."""
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


# ── CSV fixture (微信视频号) ──────────────────────────────────────────────────
WEIXIN_HEADER = [
    "视频描述", "视频ID", "发布时间", "完播率", "平均播放时长",
    "播放量", "推荐", "喜欢", "评论量", "分享量", "关注量",
    "转发聊天和朋友圈", "设为铃声", "设为状态", "设为朋友圈封面",
]
WEIXIN_ROW = [
    "原来是能吃", "export/abc123", "2026/06/23", "28.64%", "10.59秒",
    "406", "2", "2", "1", "0", "0", "0", "0", "0", "0",
]
WEIXIN_ROW2 = [
    "第二条视频", "export/def456", "2026/06/24", "12.50%", "8.30秒",
    "200", "5", "3", "0", "1", "1", "2", "0", "0", "0",
]

# ── XLSX fixture (小红书) ──────────────────────────────────────────────────────
XHS_SKIP_ROW = ["最多导出排序后前1000条笔记"]
XHS_HEADER = [
    "笔记标题", "首次发布时间", "体裁", "曝光", "观看量", "封面点击率",
    "点赞", "评论", "收藏", "涨粉", "分享", "人均观看时长", "弹幕",
]
XHS_ROW = [
    "小红书笔记一", "2026年06月25日14时50分00秒", "视频", 5000, 300,
    "6.50%", 25, 8, 12, 3, 5, "15.20秒", 2,
]


# ── Tests ──────────────────────────────────────────────────────────────────────
class TestInitCreatesTable:
    """test_init_creates_table — verifies all columns exist."""

    def test_init_creates_table(self, store):
        conn = store._conn()
        cursor = conn.execute(
            "PRAGMA table_info(video_metrics)"
        )
        columns = {row["name"] for row in cursor.fetchall()}
        conn.close()

        expected = {
            "id", "platform", "title", "platform_id", "publish_date",
            "content_type", "plays", "likes", "comments", "shares",
            "followers_gained", "completion_rate", "avg_watch_duration",
            "exposure", "cover_click_rate", "favorites", "danmaku",
            "forward_count", "extra", "job_id", "used_asset_ids",
            "imported_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

        # Verify indexes exist
        idx_cursor = conn if False else store._conn()
        indexes = [
            row["name"] for row in
            idx_cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='video_metrics'").fetchall()
        ]
        idx_cursor.close()
        assert "idx_metrics_platform" in indexes
        assert "idx_metrics_date" in indexes
        assert "idx_metrics_job" in indexes


class TestParseWeixinCSV:
    """test_parse_weixin_csv — verifies CSV import with percent/duration/date conversion."""

    def test_parse_weixin_csv(self, store):
        csv_bytes = _write_csv([WEIXIN_HEADER, WEIXIN_ROW, WEIXIN_ROW2])
        result = store.import_csv(csv_bytes, platform="weixin")

        assert result["inserted"] == 2
        assert result["updated"] == 0

        conn = store._conn()
        rows = conn.execute("SELECT * FROM video_metrics ORDER BY id").fetchall()
        conn.close()

        assert len(rows) == 2

        r1 = rows[0]
        assert r1["platform"] == "weixin"
        assert r1["title"] == "原来是能吃"
        assert r1["platform_id"] == "export/abc123"
        assert r1["publish_date"] == "2026-06-23"
        assert r1["completion_rate"] == pytest.approx(28.64)
        assert r1["avg_watch_duration"] == pytest.approx(10.59)
        assert r1["plays"] == 406
        assert r1["exposure"] == 2
        assert r1["likes"] == 2
        assert r1["comments"] == 1
        assert r1["shares"] == 0
        assert r1["followers_gained"] == 0
        assert r1["forward_count"] == 0

        r2 = rows[1]
        assert r2["title"] == "第二条视频"
        assert r2["publish_date"] == "2026-06-24"
        assert r2["completion_rate"] == pytest.approx(12.50)
        assert r2["avg_watch_duration"] == pytest.approx(8.30)


class TestParseXiaohongshuXLSX:
    """test_parse_xiaohongshu_xlsx — verifies XLSX import with datetime parsing."""

    def test_parse_xiaohongshu_xlsx(self, store, tmp_path):
        xlsx_path = _write_xlsx(
            [XHS_SKIP_ROW, XHS_HEADER, XHS_ROW],
            tmp_path / "xhs.xlsx",
        )
        result = store.import_xlsx(xlsx_path, platform="xiaohongshu")

        assert result["inserted"] == 1
        assert result["updated"] == 0

        conn = store._conn()
        rows = conn.execute("SELECT * FROM video_metrics").fetchall()
        conn.close()

        assert len(rows) == 1
        r = rows[0]
        assert r["platform"] == "xiaohongshu"
        assert r["title"] == "小红书笔记一"
        assert r["publish_date"] == "2026-06-25"
        assert r["content_type"] == "视频"
        assert r["exposure"] == 5000
        assert r["plays"] == 300
        assert r["cover_click_rate"] == pytest.approx(6.50)
        assert r["likes"] == 25
        assert r["comments"] == 8
        assert r["favorites"] == 12
        assert r["followers_gained"] == 3
        assert r["shares"] == 5
        assert r["avg_watch_duration"] == pytest.approx(15.20)
        assert r["danmaku"] == 2


class TestDedupUpdatesExisting:
    """test_dedup_updates_existing — verifies UPDATE on duplicate import."""

    def test_dedup_updates_existing(self, store):
        csv_bytes = _write_csv([WEIXIN_HEADER, WEIXIN_ROW])
        first = store.import_csv(csv_bytes, platform="weixin")
        assert first == {"inserted": 1, "updated": 0}

        # Import same row again — same (platform, title, publish_date)
        second = store.import_csv(csv_bytes, platform="weixin")
        assert second == {"inserted": 0, "updated": 1}

        conn = store._conn()
        count = conn.execute("SELECT COUNT(*) AS c FROM video_metrics").fetchone()["c"]
        conn.close()
        assert count == 1


# ── JobRecord + VideoService asset tracking tests ──────────────────────────────

def test_job_record_has_used_asset_ids():
    from packages.domain_core.models import JobRecord
    job = JobRecord(job_id="test-001", phase="queued", review_status="none")
    assert job.used_asset_ids == []
    job.used_asset_ids = ["a1", "a2"]
    assert job.used_asset_ids == ["a1", "a2"]


def test_video_service_writes_used_asset_ids():
    from packages.pipeline_services.video_service import VideoService
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        project_dir = Path(tmp)
        audio_dir = project_dir / "audio"
        audio_dir.mkdir()
        audio_file = audio_dir / "test.mp3"
        audio_file.write_bytes(b"fake audio")

        job = {
            "job_id": "test-job",
            "asset_bundle": {
                "audio_path": str(audio_file),
                "selected_clips": [
                    {"file_path": "/fake/clip1.mp4", "asset_id": "a1", "trim_start": 0, "trim_duration": 5},
                    {"file_path": "/fake/clip2.mp4", "asset_id": "a2", "trim_start": 2, "trim_duration": 8},
                ],
            },
            "used_asset_ids": [],
        }

        svc = VideoService(dry_run=True)
        output_path = project_dir / "output" / "base.mp4"
        svc.build_base_video(project_dir, job, output_path)
        assert job["used_asset_ids"] == ["a1", "a2"]
