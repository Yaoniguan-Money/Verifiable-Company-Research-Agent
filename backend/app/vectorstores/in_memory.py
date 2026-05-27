"""In-memory vector store for local development and tests."""

from __future__ import annotations

from math import sqrt

from app.vectorstores.base import VectorRecord, VectorSearchResult, VectorStore


class InMemoryVectorStore(VectorStore):
    """内存向量存储。

    - 使用 ``dict[chunk_id, VectorRecord]`` 保存记录；同 ``chunk_id`` 重复写入覆盖旧值。
    - 首次写入后锁定 ``dimension``，后续 add/search 均检查维度一致。
    - 该实现不是生产向量数据库。
    """

    def __init__(self) -> None:
        self._records: dict[str, VectorRecord] = {}
        self._dimension: int | None = None

    @property
    def dimension(self) -> int | None:
        return self._dimension

    def _validate_embedding(self, emb: list[float], *, mode: str) -> None:
        if not emb:
            raise ValueError(f"{mode} embedding 不能为空")
        if self._dimension is None:
            self._dimension = len(emb)
            return
        if len(emb) != self._dimension:
            raise ValueError(
                f"{mode} embedding 维度不一致：期望 {self._dimension}，实际 {len(emb)}"
            )

    def add_embeddings(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        for rec in records:
            self._validate_embedding(rec.embedding, mode="record")
            self._records[rec.chunk_id] = rec
        return len(records)

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        num = sum(x * y for x, y in zip(a, b, strict=False))
        na = sqrt(sum(x * x for x in a))
        nb = sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return num / (na * nb)

    def similarity_search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        task_id: str | None = None,
    ) -> list[VectorSearchResult]:
        if top_k <= 0:
            return []
        if not self._records:
            return []

        self._validate_embedding(query_embedding, mode="query")

        candidates = list(self._records.values())
        if task_id is not None:
            candidates = [r for r in candidates if r.task_id == task_id]

        scored: list[VectorSearchResult] = []
        for r in candidates:
            score = self._cosine(query_embedding, r.embedding)
            scored.append(
                VectorSearchResult(
                    chunk_id=r.chunk_id,
                    source_id=r.source_id,
                    task_id=r.task_id,
                    score=float(score),
                    metadata=r.metadata,
                )
            )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def delete(self, chunk_ids: list[str]) -> int:
        deleted = 0
        for cid in chunk_ids:
            if cid in self._records:
                del self._records[cid]
                deleted += 1
        if not self._records:
            self._dimension = None
        return deleted

    def delete_task(self, task_id: str) -> int:
        target_ids = [cid for cid, rec in self._records.items() if rec.task_id == task_id]
        return self.delete(target_ids)

    def clear(self) -> None:
        self._records.clear()
        self._dimension = None
