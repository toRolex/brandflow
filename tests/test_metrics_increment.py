"""Tests for compute_metrics_diff() — day-over-day delta computation.

Tests the pure function directly with plain dict lists, no DB dependency.
"""

from __future__ import annotations

from apps.control_plane.services.metrics import compute_metrics_diff

CURRENT_DATE = "2026-07-02"
PREVIOUS_DATE = "2026-07-01"


def _video(
    title: str,
    plays: int = 0,
    likes: int = 0,
    followers_gained: int = 0,
    shares: int = 0,
    comments: int = 0,
    platform: str = "weixin",
    publish_date: str = "2026-07-01",
) -> dict:
    return {
        "platform": platform,
        "title": title,
        "publish_date": publish_date,
        "plays": plays,
        "likes": likes,
        "followers_gained": followers_gained,
        "shares": shares,
        "comments": comments,
    }


class TestDiffUpdated:
    """Same video in both snapshots with different numbers."""

    def test_updated_delta(self):
        previous = [_video("相同视频", plays=100, likes=10, followers_gained=1, shares=2, comments=0)]
        current = [_video("相同视频", plays=150, likes=15, followers_gained=3, shares=5, comments=1)]
        result = compute_metrics_diff(previous, current, CURRENT_DATE, PREVIOUS_DATE)
        s = result["summary"]
        assert s["updated_videos"] == 1
        assert s["new_videos"] == 0
        assert s["disappeared_videos"] == 0
        assert s["plays_delta"] == 50
        assert s["likes_delta"] == 5
        assert s["followers_delta"] == 2
        assert s["shares_delta"] == 3
        assert s["comments_delta"] == 1

    def test_unchanged_not_counted_as_updated(self):
        """Videos with identical values should NOT increment updated_videos."""
        previous = [_video("未变视频", plays=100, likes=10)]
        current = [_video("未变视频", plays=100, likes=10)]
        result = compute_metrics_diff(previous, current, CURRENT_DATE, PREVIOUS_DATE)
        assert result["summary"]["updated_videos"] == 0
        assert result["summary"]["plays_delta"] == 0


class TestDiffNew:
    """Video only in the current snapshot."""

    def test_new_video(self):
        previous: list[dict] = []
        current = [_video("全新视频", plays=200, likes=20)]
        result = compute_metrics_diff(previous, current, CURRENT_DATE, PREVIOUS_DATE)
        s = result["summary"]
        assert s["new_videos"] == 1
        assert s["updated_videos"] == 0
        assert s["disappeared_videos"] == 0
        assert s["plays_delta"] == 200
        assert len(result["top_gainers"]) == 1
        assert result["top_gainers"][0]["title"] == "全新视频"


class TestDiffDisappeared:
    """Video only in the previous snapshot."""

    def test_disappeared_video(self):
        previous = [_video("消失的视频", plays=50)]
        current: list[dict] = []
        result = compute_metrics_diff(previous, current, CURRENT_DATE, PREVIOUS_DATE)
        s = result["summary"]
        assert s["disappeared_videos"] == 1
        assert s["new_videos"] == 0
        assert s["updated_videos"] == 0
        assert s["plays_delta"] == 0


class TestDiffMixed:
    """3 new + 5 updated + 1 disappeared."""

    def test_mixed_scenario(self):
        previous: list[dict] = []
        current: list[dict] = []

        # 1 disappeared — only in previous
        previous.append(_video("消失视频", plays=30, publish_date="2026-06-29"))

        # 5 updated — same titles in both
        for i in range(1, 6):
            previous.append(_video(f"更新视频{i}", plays=100 * i, likes=10 * i, publish_date=f"2026-07-0{i}"))
            current.append(_video(f"更新视频{i}", plays=100 * i + 10, likes=10 * i + 1, publish_date=f"2026-07-0{i}"))

        # 3 new — only in current
        for i in range(1, 4):
            current.append(_video(f"新视频{i}", plays=50 * i, likes=5 * i, publish_date="2026-07-02"))

        result = compute_metrics_diff(previous, current, CURRENT_DATE, PREVIOUS_DATE)
        s = result["summary"]
        assert s["new_videos"] == 3
        assert s["updated_videos"] == 5
        assert s["disappeared_videos"] == 1
        # Updated plays: 5 * 10 = 50 ; New plays: 50 + 100 + 150 = 300
        assert s["plays_delta"] == 350
        # Updated likes: 5 * 1 = 5 ; New likes: 5 + 10 + 15 = 30
        assert s["likes_delta"] == 35


class TestDiffEmpty:
    """No records in either snapshot."""

    def test_empty(self):
        result = compute_metrics_diff([], [], CURRENT_DATE, PREVIOUS_DATE)
        s = result["summary"]
        assert s["new_videos"] == 0
        assert s["updated_videos"] == 0
        assert s["disappeared_videos"] == 0
        assert s["plays_delta"] == 0
        assert result["top_gainers"] == []
        assert result["daily_trend"] == []


class TestDiffPlatformFilter:
    """compute_metrics_diff does NOT filter by platform — that's the caller's job.
    This test verifies that when only one platform's records are passed in,
    the diff correctly reflects only those records.
    """

    def test_only_weixin_records(self):
        previous = [_video("微信视频", plays=100, platform="weixin")]
        current = [_video("微信视频", plays=150, platform="weixin")]
        result = compute_metrics_diff(previous, current, CURRENT_DATE, PREVIOUS_DATE)
        assert result["summary"]["updated_videos"] == 1
        assert result["summary"]["plays_delta"] == 50

    def test_only_xiaohongshu_records(self):
        previous = [_video("小红书视频", plays=200, platform="xiaohongshu")]
        current = [_video("小红书视频", plays=250, platform="xiaohongshu")]
        result = compute_metrics_diff(previous, current, CURRENT_DATE, PREVIOUS_DATE)
        assert result["summary"]["updated_videos"] == 1
        assert result["summary"]["plays_delta"] == 50


class TestDiffTopGainers:
    """Top 10 gainers sorted by plays_delta descending."""

    def test_top_gainers_order(self):
        current = [
            _video("视频A", plays=100),
            _video("视频B", plays=200),
            _video("视频C", plays=300),
        ]
        result = compute_metrics_diff([], current, CURRENT_DATE, PREVIOUS_DATE)
        assert [g["title"] for g in result["top_gainers"]] == ["视频C", "视频B", "视频A"]

    def test_top_gainers_skip_zero(self):
        """Videos with 0 plays_delta should not appear in top_gainers."""
        current = [_video("零增长视频", plays=0)]
        result = compute_metrics_diff([], current, CURRENT_DATE, PREVIOUS_DATE)
        assert len(result["top_gainers"]) == 0


class TestDiffDailyTrend:
    """Daily trend aggregation."""

    def test_daily_trend(self):
        current = [
            _video("视频A", plays=100, publish_date="2026-07-02"),
            _video("视频B", plays=200, publish_date="2026-07-02"),
            _video("视频C", plays=300, publish_date="2026-07-01"),
        ]
        result = compute_metrics_diff([], current, CURRENT_DATE, PREVIOUS_DATE)
        assert len(result["daily_trend"]) == 2
        day1 = [d for d in result["daily_trend"] if d["date"] == "2026-07-01"][0]
        day2 = [d for d in result["daily_trend"] if d["date"] == "2026-07-02"][0]
        assert day1["plays_delta"] == 300
        assert day2["plays_delta"] == 300


class TestDiffDetail:
    """include_detail flag."""

    def test_detail_included_when_requested(self):
        current = [_video("视频A", plays=100)]
        result = compute_metrics_diff([], current, CURRENT_DATE, PREVIOUS_DATE, include_detail=True)
        assert "detail" in result
        assert len(result["detail"]) == 1

    def test_detail_omitted_by_default(self):
        current = [_video("视频A", plays=100)]
        result = compute_metrics_diff([], current, CURRENT_DATE, PREVIOUS_DATE)
        assert "detail" not in result
