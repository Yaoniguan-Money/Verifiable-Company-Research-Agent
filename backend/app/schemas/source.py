"""Source 相关 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import SchemaBase, SourceType


class SourceCreate(SchemaBase):
    task_id: str
    title: str = Field(..., min_length=1, max_length=512)
    url: str | None = Field(default=None, max_length=1024)
    source_type: SourceType
    published_at: datetime | None = None
    retrieved_at: datetime
    raw_content: str = Field(..., min_length=1)
    credibility_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_metadata: dict | None = None


class SourceRead(SchemaBase):
    id: str
    task_id: str
    title: str
    url: str | None = None
    source_type: SourceType
    published_at: datetime | None = None
    retrieved_at: datetime
    raw_content: str
    credibility_score: float | None = None
    source_metadata: dict | None = None
    created_at: datetime
