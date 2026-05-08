"""EvidenceChunk 与 Citation 相关 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import AliasChoices, Field

from app.schemas.common import SchemaBase


class Citation(SchemaBase):
    """报告引用，必须可追溯到 source 与 chunk。"""

    source_id: str
    chunk_id: str
    url: str | None = None
    title: str
    retrieved_at: datetime


class EvidenceChunkCreate(SchemaBase):
    source_id: str
    task_id: str
    chunk_index: int = Field(..., ge=0)
    text: str = Field(..., min_length=1)
    metadata: dict | None = None
    embedding_id: str | None = Field(default=None, max_length=128)


class EvidenceChunkRead(SchemaBase):
    """API 读模型：对外字段名为 ``metadata``。

    数据库 / ORM 使用物理列与属性名 ``chunk_metadata``。由于 SQLAlchemy 声明式基类上存在
    ``Base.metadata``（MetaData 对象），**禁止**对 ORM 行使用 ``EvidenceChunkRead.model_validate(row)``，
    否则易与 Pydantic 的 ``metadata`` 字段名冲突。应显式传入 ``metadata=chunk.chunk_metadata`` 或使用
    与 ``_to_chunk_read`` 等价的显式映射（物理列名不得改为 ``metadata``）。
    """
    id: str
    source_id: str
    task_id: str
    chunk_index: int
    text: str
    metadata: dict | None = Field(
        default=None,
        validation_alias=AliasChoices("metadata", "chunk_metadata"),
    )
    embedding_id: str | None = None
    created_at: datetime
