"""ResearchTask 相关 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.common import SchemaBase, TaskStatus


class ResearchTaskCreate(SchemaBase):
    company_name: str = Field(..., min_length=1, max_length=128)
    question: str = Field(..., min_length=1)
    user_id: str | None = Field(default=None)
    session_id: str | None = Field(default=None)


class ResearchTaskStatus(SchemaBase):
    task_id: str
    status: TaskStatus
    error_message: str | None = None


class ResearchTaskRead(SchemaBase):
    id: str
    user_id: str
    session_id: str | None = None
    company_name: str
    question: str
    status: TaskStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
