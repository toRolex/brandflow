"""Retrieval contract — Pydantic models for semantic segment retrieval.

Phase 1 deliverables:
  - SegmentRecord: a single searchable segment
  - RetrievalRequest: query + filters + risk policy
  - RetrievalTrace: audit log of a retrieval call with operator decision
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SegmentRecord(BaseModel):
    """A single searchable segment of video source material."""

    segment_id: str
    brand_id: str = ""
    category_id: str = ""
    product_id: str = ""
    source_id: str = ""
    source_type: str = ""
    text: str
    normalized_text: str = ""
    tags: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    created_at: str = ""


class RetrievalRequest(BaseModel):
    """A retrieval query with filters and risk policy."""

    request_id: str = ""
    project_id: str = ""
    job_id: str = ""
    task_id: str = ""
    brand_id: str = ""
    category_id: str = ""
    product_id: str = ""
    query: str
    query_type: str = ""
    top_k: int = Field(default=10, ge=1, le=100)
    filters: dict[str, Any] = Field(default_factory=dict)
    risk_policy: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class RetrievalTrace(BaseModel):
    """Audit log of a retrieval call including operator decision."""

    request_id: str = ""
    operator_decision: Literal[
        "approved", "edited", "rejected", "needs_more_evidence", "auto_approved"
    ] = "approved"
    auto_filters_applied: list[str] = Field(default_factory=list)
    manual_overrides: list[dict[str, Any]] = Field(default_factory=list)
    risk_review: dict[str, Any] = Field(default_factory=dict)
    final_context_segment_ids: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
