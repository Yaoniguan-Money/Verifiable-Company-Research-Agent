"""Research task API request and response models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chunk import Citation
from app.schemas.common import ComplianceStatus, TaskStatus
from app.schemas.fact import ExtractedFactRead
from app.schemas.source import SourceRead
from app.schemas.verification import VerificationResultRead


class CreateResearchTaskRequest(BaseModel):
    """创建研究任务请求体。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(..., min_length=1, max_length=128, description="企业名称")
    question: str = Field(..., min_length=1, description="研究问题")
    session_id: str | None = Field(default=None, description="可选：会话 ID")


class CreateResearchTaskResponse(BaseModel):
    task_id: str
    status: TaskStatus = Field(description="初始为 created")


class ResearchTaskDetailResponse(BaseModel):
    task_id: str
    company_name: str
    question: str
    status: str
    created_at: datetime
    updated_at: datetime


class RunResearchTaskResponse(BaseModel):
    task_id: str
    report_id: str | None = None
    status: str = Field(description="completed 或 failed（与数据库任务状态一致）")
    title: str | None = None
    summary: str | None = Field(default=None, description="报告内容摘要，失败时可为空")
    error: str | None = None


class ReportResponse(BaseModel):
    """GET /report 返回：经 ComplianceCheck 落库后的内容。"""

    task_id: str
    content: str
    citations: list[Citation]
    compliance_status: ComplianceStatus
    title: str | None = None


# 列表接口使用已有 Read 模型
class SourceListResponse(BaseModel):
    task_id: str
    items: list[SourceRead]


class FactListResponse(BaseModel):
    task_id: str
    items: list[ExtractedFactRead]


class VerificationListResponse(BaseModel):
    task_id: str
    items: list[VerificationResultRead]


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    task_id: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1, description="围绕当前任务报告的追问")


class ChatResponse(BaseModel):
    task_id: str
    message: str
    answer: str
    compliance_status: ComplianceStatus
    violations: list[str] = Field(default_factory=list)
