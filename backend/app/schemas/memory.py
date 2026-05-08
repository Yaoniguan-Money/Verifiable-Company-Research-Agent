"""Memory extraction operation schemas."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from app.schemas.common import SchemaBase


class MemoryOperationType(str, Enum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    NOOP = "NOOP"


class MemoryLayer(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


class MemoryOperation(SchemaBase):
    """单条记忆操作契约。"""

    op: MemoryOperationType = Field(..., description="记忆操作类型")
    memory_layer: MemoryLayer = Field(
        default=MemoryLayer.WARM,
        description="记忆层：hot 为短上下文，warm 为用户偏好，cold 为可复用知识。",
    )
    memory_type: str | None = Field(
        default=None,
        min_length=1,
        description="记忆类别，如 user_preference / risk_focus",
    )
    key: str | None = Field(default=None, min_length=1, description="记忆键")
    value: str | None = Field(default=None, min_length=1, description="记忆值")
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="提取置信度，范围 0~1",
    )
    reason: str | None = Field(default=None, min_length=1, description="操作原因")

    @model_validator(mode="after")
    def validate_by_op(self) -> MemoryOperation:
        if self.op in (MemoryOperationType.ADD, MemoryOperationType.UPDATE):
            if not self.memory_type:
                raise ValueError("ADD/UPDATE 必须包含 memory_type")
            if not self.key:
                raise ValueError("ADD/UPDATE 必须包含 key")
            if not self.value:
                raise ValueError("ADD/UPDATE 必须包含 value")
            if not self.reason:
                raise ValueError("ADD/UPDATE 必须包含 reason")
            return self

        if self.op == MemoryOperationType.DELETE:
            if not self.memory_type:
                raise ValueError("DELETE 必须包含 memory_type")
            if not self.key:
                raise ValueError("DELETE 必须包含 key")
            if not self.reason:
                raise ValueError("DELETE 必须包含 reason")
            return self

        if self.op == MemoryOperationType.NOOP:
            if not self.reason:
                raise ValueError("NOOP 必须包含 reason")
            return self

        return self


class MemoryExtractionOutput(SchemaBase):
    """温记忆提取输出契约。"""

    operations: list[MemoryOperation] = Field(
        ...,
        min_length=1,
        description="本轮提取得到的记忆操作列表，不允许为空",
    )
