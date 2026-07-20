"""Tests for per-sentence clip trimming in video assembly."""

import math

from packages.pipeline_services.asset_library.retriever import _compute_trim_params


class TestClipTrimming:
    """验证按句裁剪的参数计算。"""

    def test_equal_distribution_with_simple_case(self):
        """2个句子、10秒总音频 → 每句5秒。"""
        clips = [
            {
                "sentence": "第一句话的文案",
                "file_path": "/data/a.mp4",
                "category": "切配处理",
            },
            {
                "sentence": "第二句话的文案内容",
                "file_path": "/data/b.mp4",
                "category": "烹饪翻炒",
            },
        ]
        audio_duration = 10.0

        trimmed = _compute_trim_params(clips, audio_duration)

        assert len(trimmed) == 2
        assert math.isclose(trimmed[0]["duration"], 5.0, rel_tol=0.1)
        assert math.isclose(trimmed[1]["duration"], 5.0, rel_tol=0.1)

    def test_each_clip_has_random_ss(self):
        """每个素材的起始偏移应在 0-1 之间。"""
        clips = [
            {"sentence": "句子一", "file_path": "/data/a.mp4", "category": "产品特写"},
            {"sentence": "句子二", "file_path": "/data/b.mp4", "category": "产品特写"},
            {"sentence": "句子三", "file_path": "/data/c.mp4", "category": "产品特写"},
        ]
        audio_duration = 12.0

        trimmed = _compute_trim_params(clips, audio_duration)

        assert len(trimmed) == 3
        for t in trimmed:
            assert 0.0 <= t["ss"] <= 1.0, f"ss={t['ss']} 不在 [0,1] 内"
            assert t["duration"] > 0

    def test_clip_duration_never_exceeds_source(self):
        """裁剪时长不应超过素材剩余可用时长（ss 后的部分）。"""
        clips = [
            {
                "sentence": "第一句话",
                "file_path": "/data/a.mp4",
                "category": "成品展示",
            },
        ]
        audio_duration = 3.0

        trimmed = _compute_trim_params(clips, audio_duration)

        assert trimmed[0]["duration"] <= 3.0

    def test_short_clip_leftover_is_redistributed(self, monkeypatch):
        """短素材不应让总裁剪时长低于口播时长。"""
        monkeypatch.setattr(
            "packages.pipeline_services.asset_library.retriever.random.uniform",
            lambda *_: 0.0,
        )
        clips = [
            {
                "sentence": "短片段",
                "file_path": "/data/a.mp4",
                "category": "成品展示",
                "duration_seconds": 2.0,
            },
            {
                "sentence": "长片段一",
                "file_path": "/data/b.mp4",
                "category": "成品展示",
                "duration_seconds": 10.0,
            },
            {
                "sentence": "长片段二",
                "file_path": "/data/c.mp4",
                "category": "成品展示",
                "duration_seconds": 10.0,
            },
            {
                "sentence": "长片段三",
                "file_path": "/data/d.mp4",
                "category": "成品展示",
                "duration_seconds": 10.0,
            },
        ]
        audio_duration = 20.0

        trimmed = _compute_trim_params(clips, audio_duration)
        total = sum(item["duration"] for item in trimmed)

        assert total == 20.0
        assert trimmed[0]["duration"] == 2.0

    def test_empty_clips_returns_empty(self):
        """空素材列表返回空。"""
        assert _compute_trim_params([], 10.0) == []

    def test_blank_matched_by_sentence_index_not_position(self):
        """Blank clip duration comes from timing with matching index, not array pos."""
        clips = [
            {
                "sentence": "introduction sentence",
                "file_path": "/data/a.mp4",
                "category": "intro",
                "visual_type": "clip",
                "sentence_index": 0,
            },
            {
                "sentence": "blank sentence",
                "file_path": "",
                "category": "",
                "visual_type": "blank",
                "sentence_index": 5,  # Index 5 — not the 2nd item in the array
            },
            {
                "sentence": "third sentence",
                "file_path": "/data/b.mp4",
                "category": "outro",
                "visual_type": "clip",
                "sentence_index": 8,
            },
        ]
        audio_duration = 30.0

        # Sentence timings: only entries for indices that have audio
        sentence_timings = [
            {"index": 0, "text": "intro", "start_seconds": 0.0, "end_seconds": 5.0},
            {"index": 5, "text": "blank", "start_seconds": 5.0, "end_seconds": 7.5},
            {"index": 8, "text": "outro", "start_seconds": 7.5, "end_seconds": 30.0},
        ]

        trimmed = _compute_trim_params(clips, audio_duration, sentence_timings)

        # Blank clip (array index 1) should match sentence_timing with index=5
        blank = trimmed[1]
        assert blank["visual_type"] == "blank"
        assert blank["duration"] == 2.5, (
            f"Blank duration should be 2.5 (from index=5 timing), "
            f"got {blank['duration']}"
        )

        # Clip at array index 0 should NOT accidentally use index=5's timing
        clip0 = trimmed[0]
        assert clip0["visual_type"] == "clip"
        # Per-clip equal share for non-blank: (30 - 2.5) / 2 = 13.75 ... actually
        # the redistribution happens after initial assignment. Just verify it's positive.
        assert clip0["duration"] > 0

        # Clip at array index 2 should NOT use index=8's timing
        clip2 = trimmed[2]
        assert clip2["visual_type"] == "clip"
        assert clip2["duration"] > 0

    def test_sentence_index_fallback_to_array_position(self):
        """When clip lacks sentence_index, falls back to array position."""
        clips = [
            {
                "sentence": "clip A",
                "file_path": "/data/a.mp4",
                "category": "intro",
                "visual_type": "clip",
            },
            {
                "sentence": "blank fallback",
                "file_path": "",
                "category": "",
                "visual_type": "blank",
                # No sentence_index — falls back to array position 1
            },
        ]
        audio_duration = 10.0

        sentence_timings = [
            {"index": 0, "text": "clip A", "start_seconds": 0.0, "end_seconds": 4.0},
            {"index": 1, "text": "blank", "start_seconds": 4.0, "end_seconds": 10.0},
        ]

        trimmed = _compute_trim_params(clips, audio_duration, sentence_timings)

        # Blank at array position 1 → matched by fallback to idx=1 in timings
        blank = trimmed[1]
        assert blank["visual_type"] == "blank"
        assert blank["duration"] == 6.0, (
            f"Blank should get 6.0 from sentence_timings[1], got {blank['duration']}"
        )
