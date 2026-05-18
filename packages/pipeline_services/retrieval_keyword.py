"""Keyword-based retrieval scoring.

Task 7: keyword_score(query, segment) — tag overlap + substring match.
"""

from __future__ import annotations

from packages.pipeline_services.retrieval_contract import SegmentRecord


def keyword_score(query: str, segment: SegmentRecord) -> float:
    """Score a segment against a keyword query.

    Scoring heuristics (cumulative, capped at 1.0):
      - Tag match: each query token that appears (case-insensitive) in
        segment.tags earns +0.6.
      - Text match: each query token that appears as a substring in
        segment.text earns +0.2.

    Returns 0.0 when nothing matches.
    """
    query_lower = query.lower()
    tokens = query_lower.split()
    if not tokens:
        return 0.0

    score = 0.0
    tag_lower = [t.lower() for t in segment.tags]
    text_lower = segment.text.lower()

    for token in tokens:
        if any(token in t for t in tag_lower):
            score += 0.6
        if token in text_lower:
            score += 0.2

    return min(score, 1.0)
