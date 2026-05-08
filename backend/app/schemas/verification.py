"""VerificationResult 相关 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.schemas.common import SchemaBase, VerificationStatus


class VerificationResultBase(SchemaBase):
    """验证结果公共字段（3.C 状态机约束基线）。"""

    fact_id: str
    task_id: str
    status: VerificationStatus
    confidence: float = Field(..., ge=0.0, le=1.0)
    supporting_sources: list[str] = Field(default_factory=list)
    conflicting_sources: list[str] = Field(default_factory=list)
    reason: str = Field(..., min_length=1)
    reason_code: str | None = None

    @model_validator(mode="after")
    def validate_status_state(self) -> VerificationResultBase:
        # 3.C 最小状态机约束：仅做字段层约束，不实现完整验证算法。
        if self.status == VerificationStatus.VERIFIED and not self.supporting_sources:
            raise ValueError("verified 状态至少应包含一条 supporting_sources")
        if self.status == VerificationStatus.CONFLICTED and not self.conflicting_sources:
            raise ValueError("conflicted 状态至少应包含一条 conflicting_sources")
        return self


class VerificationResultCreate(VerificationResultBase):
    """写入 verification_results 的创建模型。"""


class VerificationResultRead(VerificationResultBase):
    """读取 verification_results 的响应模型。"""

    id: str
    created_at: datetime


class VerificationInput(SchemaBase):
    """可选：单条 fact 的验证输入契约。"""

    task_id: str
    fact_id: str
    claim: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    metric_name: str | None = None
    value: str | None = None
    period: str | None = None


class VerificationOutput(SchemaBase):
    """可选：批量验证输出契约。"""

    task_id: str
    results: list[VerificationResultCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_task_consistency(self) -> VerificationOutput:
        for item in self.results:
            if item.task_id != self.task_id:
                raise ValueError("results 中存在 task_id 与输出 task_id 不一致的记录")
        return self
