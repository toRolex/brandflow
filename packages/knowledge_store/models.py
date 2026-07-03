from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    """Supported source document types."""

    TXT = "txt"
    PDF = "pdf"
    DOCX = "docx"


class KnowledgeItemType(str, Enum):
    """Knowledge item types for extracted information."""

    SELLING_POINT = "selling_point"
    SPECIFICATION = "specification"
    FORBIDDEN_WORD = "forbidden_word"
    BRAND_TONE = "brand_tone"
    USAGE_SCENE = "usage_scene"


class KnowledgeDocument(BaseModel):
    """Represents an uploaded knowledge document (TXT file)."""

    id: str
    filename: str
    source_type: SourceType = SourceType.TXT
    parsed_text: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "KnowledgeDocument":
        return KnowledgeDocument(**data)


class KnowledgeItem(BaseModel):
    """A single knowledge item extracted from a document."""

    id: str
    document_id: str
    type: KnowledgeItemType
    title: str
    content: str
    priority: int = Field(default=3, ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    source_document: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = self.model_dump()
        d["type"] = self.type.value
        return d

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "KnowledgeItem":
        return KnowledgeItem(**data)


class KnowledgeConfig(BaseModel):
    """Configuration for knowledge injection into script generation."""

    enabled: bool = True
    top_k: int = Field(default=5, ge=1, le=20)
