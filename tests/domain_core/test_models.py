"""Tests for VisualType and AssetPosition — the three-state asset review model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from packages.domain_core.models import AssetPosition, VisualType


class TestVisualType:
    def test_clip_is_valid_value(self) -> None:
        # VisualType is a Literal type alias — verify the values exist
        clip: VisualType = "clip"
        assert clip == "clip"

    def test_blank_is_valid_value(self) -> None:
        blank: VisualType = "blank"
        assert blank == "blank"

    def test_unresolved_is_valid_value(self) -> None:
        unresolved: VisualType = "unresolved"
        assert unresolved == "unresolved"

    def test_invalid_visual_type_raises(self) -> None:
        with pytest.raises(ValidationError):
            AssetPosition(sentence="test", visual_type="invalid")  # type: ignore[arg-type]


class TestAssetPosition:
    def test_clip_position(self) -> None:
        pos = AssetPosition(
            sentence="这是第一句。",
            category="intro",
            file_path="/data/clip.mp4",
            asset_id="asset-001",
            duration_seconds=5.0,
            method="llm_match",
            visual_type="clip",
            requested_category="开场",
        )
        assert pos.visual_type == "clip"
        assert pos.file_path == "/data/clip.mp4"
        assert pos.asset_id == "asset-001"

    def test_blank_position_has_no_path(self) -> None:
        pos = AssetPosition(
            sentence="这是空白段落。",
            visual_type="blank",
        )
        assert pos.visual_type == "blank"
        assert pos.file_path == ""
        assert pos.asset_id == ""

    def test_unresolved_position(self) -> None:
        pos = AssetPosition(
            sentence="找不到素材的句子。",
            visual_type="unresolved",
        )
        assert pos.visual_type == "unresolved"
        assert pos.file_path == ""

    def test_default_visual_type_is_unresolved(self) -> None:
        pos = AssetPosition(sentence="默认句子。")
        assert pos.visual_type == "unresolved"

    def test_sentence_is_required(self) -> None:
        with pytest.raises(ValidationError):
            AssetPosition()

    def test_sentence_index_defaults_to_zero(self) -> None:
        pos = AssetPosition(sentence="默认句子。")
        assert pos.sentence_index == 0

    def test_sentence_index_explicit(self) -> None:
        pos = AssetPosition(sentence="第3句。", sentence_index=3)
        assert pos.sentence_index == 3

    def test_sentence_index_is_serialized(self) -> None:
        pos = AssetPosition(sentence="第5句。", sentence_index=5)
        d = pos.model_dump()
        assert d["sentence_index"] == 5
