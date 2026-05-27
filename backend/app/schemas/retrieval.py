"""Retrieval service output schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import SchemaBase


class RetrievedEvidence(SchemaBase):
    """单条检索证据。

    仅用于业务检索返回，不等同报告 citation。
    """

    chunk_id: str
    source_id: str
    task_id: str
    text: str = Field(..., min_length=1)
    score: float
    source_title: str
    source_url: str | None = None
    source_type: str
    retrieved_at: datetime
    metadata: dict | None = None

