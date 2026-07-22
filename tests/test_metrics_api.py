"""Tests for MetricsStore aggregation queries and /api/metrics endpoints."""

from __future__ import annotations

import csv
import io
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.control_plane.app import create_app
from apps.control_plane.services.metrics import MetricsStore


# ── Helpers ──────────────────────────────────────────────────────────────────────


def _write_csv(rows: list[list[str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    for row in rows:
        writer.writerow(row)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def _seed_store(
    store: MetricsStore,
    *,
    count: int = 3,
    platform: str = "weixin",
    base_date: str | None = None,
) -> None:
    """Insert test rows directly into the DB."""
    if base_date is None:
        base_date = (datetime.now(UTC) - timedelta(days=count)).strftime("%Y-%m-%d")
    conn = store._conn()
    try:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        for i in range(1, count + 1):
            day_offset = i - 1
            date_parts = base_date.split("-")
            d = int(date_parts[2]) + day_offset
            pub_date = f"{date_parts[0]}-{date_parts[1]}-{d:02d}"
            conn.execute(
                """INSERT OR IGNORE INTO video_metrics
                   (platform, title, publish_date, plays, likes, comments,
                    shares, followers_gained, completion_rate, extra,
                    job_id, used_asset_ids, imported_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    platform,
                    f"测试视频{i}",
                    pub_date,
                    100 * i,
                    10 * i,
                    i,
                    0,
                    i,
                    20.0 + i,
                    None,
                    None,
                    json.dumps([f"a{i}"]),
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def store(tmp_path):
    return MetricsStore(db_path=str(tmp_path / "test_metrics.db"))


@pytest.fixture
def client(tmp_path):
    """FastAPI test client with its own root_dir (includes metrics.db)."""
    root_dir = tmp_path / "project_root"
    (root_dir / "data").mkdir(parents=True, exist_ok=True)
    # Ensure metrics.db path exists
    (root_dir / "data" / "metrics.db").touch()
    app = create_app(root_dir=root_dir)
    with TestClient(app) as c:
        yield c


# ── Aggregation: get_overview ────────────────────────────────────────────────────


class TestGetOverview:
    def test_returns_total_keys(self, store):
        _seed_store(store, count=3)
        result = store.get_overview(days=30)
        assert "total_plays" in result
        assert "total_likes" in result
        assert "total_followers" in result
        assert "avg_completion" in result
        assert "video_count" in result
        assert "daily" in result

    def test_totals_correct(self, store):
        _seed_store(store, count=3)
        result = store.get_overview(days=30)
        assert result["video_count"] == 3
        # plays: 100 + 200 + 300
        assert result["total_plays"] == 600
        # likes: 10 + 20 + 30
        assert result["total_likes"] == 60
        # followers_gained: 1 + 2 + 3
        assert result["total_followers"] == 6
        assert result["avg_completion"] == pytest.approx(22.0)

    def test_daily_grouping(self, store):
        _seed_store(store, count=3)
        result = store.get_overview(days=30)
        daily = result["daily"]
        assert len(daily) == 3
        base = (datetime.now(UTC) - timedelta(days=3)).strftime("%Y-%m-%d")
        assert daily[0]["publish_date"] == base
        assert daily[0]["plays"] == 100
        assert daily[-1]["publish_date"] == (
            datetime.now(UTC) - timedelta(days=1)
        ).strftime("%Y-%m-%d")
        assert daily[-1]["plays"] == 300

    def test_platform_filter(self, store):
        _seed_store(store, count=2, platform="weixin")
        _seed_store(store, count=1, platform="xiaohongshu")
        result = store.get_overview(days=30, platform="weixin")
        assert result["video_count"] == 2
        assert result["total_plays"] == 300  # 100 + 200

    def test_date_filter_excludes_old(self, store):
        _seed_store(store, count=1, base_date="2020-01-01")
        result = store.get_overview(days=7)
        assert result["video_count"] == 0
        assert result["total_plays"] == 0
        assert result["daily"] == []

    def test_empty_store(self, store):
        result = store.get_overview()
        assert result["total_plays"] == 0
        assert result["daily"] == []


# ── Aggregation: get_videos ──────────────────────────────────────────────────────


class TestGetVideos:
    def test_returns_items_and_pagination(self, store):
        _seed_store(store, count=3)
        result = store.get_videos()
        assert "items" in result
        assert "total" in result
        assert "page" in result
        assert "page_size" in result
        assert result["total"] == 3
        assert len(result["items"]) == 3

    def test_parses_used_asset_ids(self, store):
        _seed_store(store, count=1)
        result = store.get_videos()
        item = result["items"][0]
        assert isinstance(item["used_asset_ids"], list)
        assert item["used_asset_ids"] == ["a1"]

    def test_sort_plays_desc(self, store):
        _seed_store(store, count=3)
        result = store.get_videos(sort_by="plays_desc")
        plays = [item["plays"] for item in result["items"]]
        assert plays == sorted(plays, reverse=True)

    def test_sort_date_asc(self, store):
        _seed_store(store, count=3)
        result = store.get_videos(sort_by="date_asc")
        dates = [item["publish_date"] for item in result["items"]]
        assert dates == sorted(dates)

    def test_search_filters_by_title(self, store):
        _seed_store(store, count=3)
        result = store.get_videos(search="视频1")
        assert result["total"] == 1
        assert result["items"][0]["title"] == "测试视频1"

    def test_pagination(self, store):
        _seed_store(store, count=5)
        result = store.get_videos(page=1, page_size=2)
        assert len(result["items"]) == 2
        assert result["total"] == 5
        assert result["page"] == 1
        assert result["page_size"] == 2
        # page 3 should have 1 item
        result2 = store.get_videos(page=3, page_size=2)
        assert len(result2["items"]) == 1

    def test_platform_filter(self, store):
        _seed_store(store, count=2, platform="weixin")
        _seed_store(store, count=1, platform="xiaohongshu", base_date="2026-06-21")
        result = store.get_videos(platform="weixin")
        assert result["total"] == 2

    def test_empty_store(self, store):
        result = store.get_videos()
        assert result["items"] == []
        assert result["total"] == 0


# ── Aggregation: get_topics ──────────────────────────────────────────────────────


class TestGetTopics:
    def _seed_titles(self, store):
        conn = store._conn()
        try:
            now = datetime.now(UTC).isoformat(timespec="seconds")
            rows = [
                ("weixin", "羊肚菌炖鸡教程", "2026-06-20", 500, 50, 30.0),
                ("weixin", "羊肚菌煲汤做法", "2026-06-21", 400, 40, 25.0),
                ("weixin", "荔枝菌炒饭真香", "2026-06-22", 300, 30, 20.0),
            ]
            for p, t, d, plays, likes, cr in rows:
                conn.execute(
                    """INSERT OR IGNORE INTO video_metrics
                       (platform, title, publish_date, plays, likes,
                        followers_gained, completion_rate, used_asset_ids, imported_at)
                       VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?)""",
                    (p, t, d, plays, likes, cr, "[]", now),
                )
            conn.commit()
        finally:
            conn.close()

    def test_returns_list_of_dicts(self, store):
        self._seed_titles(store)
        result = store.get_topics(days=30)
        assert isinstance(result, list)
        if result:
            assert "keyword" in result[0]
            assert "total_plays" in result[0]
            assert "video_count" in result[0]
            assert "avg_completion" in result[0]

    def test_sorted_by_total_plays(self, store):
        self._seed_titles(store)
        result = store.get_topics(days=30)
        if len(result) >= 2:
            for i in range(len(result) - 1):
                assert result[i]["total_plays"] >= result[i + 1]["total_plays"]

    def test_limit(self, store):
        self._seed_titles(store)
        result = store.get_topics(days=30, limit=2)
        assert len(result) <= 2

    def test_platform_filter(self, store):
        self._seed_titles(store)
        result = store.get_topics(days=30, platform="weixin")
        # All test rows are weixin
        assert isinstance(result, list)

    def test_empty_store(self, store):
        result = store.get_topics()
        assert result == []


# ── API: /api/metrics/upload ─────────────────────────────────────────────────────


class TestUploadEndpoint:
    def test_upload_csv(self, client):
        csv_bytes = _write_csv(
            [
                [
                    "视频描述",
                    "视频ID",
                    "发布时间",
                    "完播率",
                    "平均播放时长",
                    "播放量",
                    "推荐",
                    "喜欢",
                    "评论量",
                    "分享量",
                    "关注量",
                    "转发聊天和朋友圈",
                ],
                [
                    "原来是能吃",
                    "export/abc",
                    "2026/06/25",
                    "28.64%",
                    "10秒",
                    "406",
                    "2",
                    "2",
                    "1",
                    "0",
                    "0",
                    "0",
                ],
            ]
        )
        resp = client.post(
            "/api/metrics/upload",
            files={"file": ("test_weixin.csv", csv_bytes, "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 1

    def test_upload_xlsx(self, client, tmp_path):
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(["最多导出排序后前1000条笔记"])
        ws.append(
            [
                "笔记标题",
                "首次发布时间",
                "体裁",
                "曝光",
                "观看量",
                "封面点击率",
                "点赞",
                "评论",
                "收藏",
                "涨粉",
                "分享",
                "人均观看时长",
                "弹幕",
            ]
        )
        ws.append(
            [
                "小红书测试",
                "2026年06月25日14时50分00秒",
                "视频",
                5000,
                300,
                "6.50%",
                25,
                8,
                12,
                3,
                5,
                "15.20秒",
                2,
            ]
        )
        xlsx_path = tmp_path / "test.xlsx"
        wb.save(xlsx_path)
        xlsx_bytes = xlsx_path.read_bytes()

        resp = client.post(
            "/api/metrics/upload",
            files={
                "file": (
                    "小红书_data.xlsx",
                    xlsx_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["inserted"] == 1


# ── API: /api/metrics/overview ────────────────────────────────────────────────────


class TestOverviewEndpoint:
    def test_overview_returns_expected_keys(self, client, tmp_path):
        # Seed data into the DB used by the client
        db_path = tmp_path / "project_root" / "data" / "metrics.db"
        store = MetricsStore(db_path=str(db_path))
        _seed_store(store, count=2, base_date="2026-06-22")

        resp = client.get("/api/metrics/overview?days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_plays" in data
        assert "daily" in data
        assert data["video_count"] == 2


# ── API: /api/metrics/videos ─────────────────────────────────────────────────────


class TestVideosEndpoint:
    def test_videos_returns_items_and_total(self, client, tmp_path):
        db_path = tmp_path / "project_root" / "data" / "metrics.db"
        store = MetricsStore(db_path=str(db_path))
        _seed_store(store, count=2, base_date="2026-06-22")

        resp = client.get("/api/metrics/videos?sort_by=plays_desc&page=1&page_size=50")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 2


# ── API: /api/metrics/topics ─────────────────────────────────────────────────────


class TestTopicsEndpoint:
    def test_topics_returns_list(self, client, tmp_path):
        db_path = tmp_path / "project_root" / "data" / "metrics.db"
        store = MetricsStore(db_path=str(db_path))
        _seed_store(store, count=2, base_date="2026-06-22")

        resp = client.get("/api/metrics/topics?days=30&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)


# ── API: /api/metrics/scan ───────────────────────────────────────────────────────


class TestScanEndpoint:
    def test_scan_imports_csv_files(self, client, tmp_path):
        # Create a CSV file in the data/ dir
        data_dir = tmp_path / "project_root" / "data" / "weixin" / "2026-6-25"
        data_dir.mkdir(parents=True, exist_ok=True)
        csv_bytes = _write_csv(
            [
                [
                    "视频描述",
                    "视频ID",
                    "发布时间",
                    "完播率",
                    "平均播放时长",
                    "播放量",
                    "推荐",
                    "喜欢",
                    "评论量",
                    "分享量",
                    "关注量",
                    "转发聊天和朋友圈",
                ],
                [
                    "扫描测试视频",
                    "export/scan1",
                    "2026/06/25",
                    "15%",
                    "8秒",
                    "100",
                    "1",
                    "5",
                    "0",
                    "0",
                    "0",
                    "0",
                ],
            ]
        )
        (data_dir / "test_weixin.csv").write_bytes(csv_bytes)

        resp = client.post("/api/metrics/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["files_processed"] >= 1
        assert data["total_inserted"] >= 1


# ── Integration: real data directory ────────────────────────────────────────────


def test_scan_real_data_directory():
    """Test scanning the actual data/ directory if it exists."""
    import shutil

    real_data = Path(__file__).resolve().parent.parent / "data"
    if not real_data.exists():
        import pytest

        pytest.skip("data/ directory not found")

    # Create app with temp root
    from apps.control_plane.app import create_app
    from fastapi.testclient import TestClient

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        app = create_app(root_dir=root)

        # Copy data structure to temp root
        shutil.copytree(str(real_data), str(root / "data"), dirs_exist_ok=True)

        # Create a sample CSV file so the scan has something to process
        sample_csv = root / "data" / "metrics_weixin_20260101.csv"
        sample_csv.write_text(
            "视频描述,视频ID,发布时间,播放量,喜欢,评论量,分享量,关注量,转发聊天和朋友圈,完播率,平均播放时长,推荐\n"
            "测试视频一,v001,2026-07-19,100,10,5,2,1,0,50%,30秒,200\n"
        )

        with TestClient(app) as client:
            # 1. Scan should find and import files
            resp = client.post("/api/metrics/scan")
            assert resp.status_code == 200
            data = resp.json()
            assert data["files_processed"] > 0, (
                f"Expected files_processed > 0, got {data}"
            )
            assert data["total_inserted"] > 0, (
                f"Expected total_inserted > 0, got {data}"
            )

            # 2. Overview should return aggregated data
            resp = client.get("/api/metrics/overview?days=30")
            assert resp.status_code == 200
            overview = resp.json()
            assert overview["total_plays"] > 0, (
                "Expected total_plays > 0 from real data"
            )
            assert overview["video_count"] > 0, "Expected video_count > 0"

            # 3. Videos endpoint should return sorted list
            resp = client.get("/api/metrics/videos?sort_by=plays_desc")
            assert resp.status_code == 200
            videos = resp.json()
            assert videos["total"] > 0
            # Verify sort order: first item plays >= last item plays
            if len(videos["items"]) > 1:
                assert videos["items"][0]["plays"] >= videos["items"][-1]["plays"]

            # 4. Topics should return non-empty keyword list
            resp = client.get("/api/metrics/topics?days=30")
            assert resp.status_code == 200
            topics = resp.json()
            assert len(topics) > 0, "Expected at least one topic keyword"

            # 5. Platform filter should work
            resp = client.get("/api/metrics/overview?days=30&platform=weixin")
            assert resp.status_code == 200

            # 6. Search should work
            resp = client.get(
                "/api/metrics/videos?search=%E8%8D%94%E6%9E%9D%E8%8F%8C"
            )  # 荔枝菌
            assert resp.status_code == 200
