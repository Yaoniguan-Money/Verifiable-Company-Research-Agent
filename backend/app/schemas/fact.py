"""ExtractedFact schemas shared by extraction, persistence, and API output."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.schemas.common import SchemaBase


class ExtractedFactBase(SchemaBase):
    """事实公共字段：用于 Create / Read / 抽取输出统一复用。"""

    task_id: str
    claim: str = Field(..., min_length=1)
    metric_name: str | None = Field(default=None, max_length=128)
    value: str | None = Field(default=None, max_length=256)
    period: str | None = Field(default=None, max_length=64)
    source_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)


class ExtractedFactCreate(ExtractedFactBase):
    """用于写入 extracted_facts 的创建模型。"""


class ExtractedFactRead(ExtractedFactBase):
    """用于 API/服务层读取的事实模型。"""

    id: str
    created_at: datetime


class ExtractedFactExtractionInput(SchemaBase):
    """单次抽取输入：约束抽取必须绑定 task/source/chunk。"""

    task_id: str
    source_id: str = Field(..., min_length=1)
    chunk_id: str = Field(..., min_length=1)
    chunk_text: str = Field(..., min_length=1)
    company_name: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1)


class ExtractedFactExtractionOutput(SchemaBase):
    """单次抽取输出：承载结构化事实列表。"""

    task_id: str
    facts: list[ExtractedFactCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_fact_task_ids(self) -> ExtractedFactExtractionOutput:
        # 保证输出中的事实不会串 task。
        for fact in self.facts:
            if fact.task_id != self.task_id:
                raise ValueError("facts 中存在与输出 task_id 不一致的记录")
        return self
