"""Report 相关 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.chunk import Citation
from app.schemas.common import ComplianceStatus, SchemaBase


class ReportCreate(SchemaBase):
    task_id: str
    title: str = Field(..., min_length=1, max_length=512)
    content: str = Field(..., min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    compliance_status: ComplianceStatus = ComplianceStatus.SKIPPED


class ReportRead(SchemaBase):
    id: str
    task_id: str
    title: str
    content: str
    citations: list[Citation]
    compliance_status: ComplianceStatus
    created_at: datetime
