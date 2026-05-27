"""Vector-store abstraction and shared data structures."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """向量写入记录（底层 primitive）。"""

    chunk_id: str
    source_id: str
    task_id: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VectorSearchResult:
    """向量检索结果（底层 primitive，不等于业务 retrieval 结果）。"""

    chunk_id: str
    source_id: str
    task_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """可替换向量存储接口。

    只定义底层向量操作；业务检索编排由 ``RetrievalService`` 负责。
    """

    @property
    @abstractmethod
    def dimension(self) -> int | None:
        """当前向量维度；空库可为 ``None``。"""

    @abstractmethod
    def add_embeddings(self, records: list[VectorRecord]) -> int:
        """写入多条向量记录，返回成功写入条数。"""

    @abstractmethod
    def similarity_search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        task_id: str | None = None,
    ) -> list[VectorSearchResult]:
        """按相似度降序返回结果，支持 ``task_id`` 精确过滤。"""

    @abstractmethod
    def delete(self, chunk_ids: list[str]) -> int:
        """按 chunk_id 删除并返回删除条数。"""

    @abstractmethod
    def delete_task(self, task_id: str) -> int:
        """按 task_id 删除该任务的全部向量记录，返回删除条数。"""

    @abstractmethod
    def clear(self) -> None:
        """清空存储（主要供测试使用）。"""
