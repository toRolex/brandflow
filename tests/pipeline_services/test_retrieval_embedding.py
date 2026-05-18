"""Tests for retrieval_embedding and retrieval_keyword."""

import math

import pytest

from packages.pipeline_services.retrieval_contract import SegmentRecord
from packages.pipeline_services.retrieval_embedding import cosine_similarity
from packages.pipeline_services.retrieval_keyword import keyword_score


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        v = [1.0, 2.0, 3.0]
        assert math.isclose(cosine_similarity(v, v), 1.0, rel_tol=1e-9)

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        assert math.isclose(cosine_similarity(a, b), 0.0, abs_tol=1e-9)

    def test_opposite_vectors(self) -> None:
        a = [1.0, 2.0]
        b = [-1.0, -2.0]
        assert math.isclose(cosine_similarity(a, b), -1.0, rel_tol=1e-9)

    def test_positive_similarity(self) -> None:
        a = [1.0, 0.0]
        b = [1.0, 1.0]
        expected = (1.0 * 1.0 + 0.0 * 1.0) / (1.0 * math.sqrt(2))
        assert math.isclose(cosine_similarity(a, b), expected, rel_tol=1e-9)

    def test_zero_vector_raises(self) -> None:
        with pytest.raises(ValueError):
            cosine_similarity([0.0, 0.0], [1.0, 2.0])
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 2.0], [0.0, 0.0])

    def test_mismatched_dimensions_raises(self) -> None:
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


class TestKeywordScore:
    def _make_segment(self, text: str, tags: list[str] | None = None) -> SegmentRecord:
        return SegmentRecord(
            segment_id="test-seg",
            text=text,
            tags=tags or [],
        )

    def test_exact_tag_match_scores_high(self) -> None:
        seg = self._make_segment("充分烹熟后食用见手青。", tags=["见手青"])
        score = keyword_score("见手青", seg)
        assert score > 0.5

    def test_text_substring_match(self) -> None:
        seg = self._make_segment("滋元堂为您带来高品质羊肚菌。", tags=[])
        score = keyword_score("羊肚菌", seg)
        assert score > 0.0

    def test_no_match_returns_zero(self) -> None:
        seg = self._make_segment("日常饮食小贴士。", tags=["健康"])
        score = keyword_score("见手青", seg)
        assert score == 0.0

    def test_multiple_tag_matches_score_higher(self) -> None:
        seg = self._make_segment("见手青需要充分烹熟。", tags=["见手青", "安全", "烹饪"])
        score_multi = keyword_score("见手青 安全", seg)
        score_single = keyword_score("见手青", seg)
        assert score_multi >= score_single

    def test_case_insensitive(self) -> None:
        seg = self._make_segment("见手青安全指南", tags=["见手青"])
        score_lower = keyword_score("见手青", seg)
        score_upper = keyword_score("见手青".upper(), seg)
        assert score_lower == score_upper
