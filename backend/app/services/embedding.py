"""Generate embeddings for evidence chunks and persist stable embedding IDs."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import EvidenceChunk
from app.providers.embedding.base import EmbeddingProvider
from app.repositories import ResearchArtifactRepository


@dataclass(frozen=True, slots=True)
class ChunkEmbeddingResult:
    """单次切片对应的向量结果（供测试/调试）；向量本体不写入 ``chunk_metadata``。"""

    chunk_id: str
    embedding_id: str
    vector: list[float]
    dimension: int


class EmbeddingService:
    """调用 ``EmbeddingProvider`` 计算向量，并仅更新 ``EvidenceChunk.embedding_id``。

    - **不** 将 ``list[float]`` 写入 ``chunk_metadata``；后续向量持久化应走专库/专列，不把 metadata 当作长期主存。
    - 会**修改**传入的 ``db`` session（更新行 + ``flush``），**不** ``commit``；**事务边界由调用方**负责。

    不做：vector store、similarity、retrieval、citation 候选、报告 grounding。
    """

    def __init__(self, db: Session, provider: EmbeddingProvider) -> None:
        self.db = db
        self._provider = provider
        self.artifacts = ResearchArtifactRepository(db)

    def embed_and_persist_ids(self, chunks: list[EvidenceChunk]) -> list[ChunkEmbeddingResult]:
        """对已有 ORM 行按 ``chunk.text`` 算向量，并**覆盖**写入 ``embedding_id``。

        早期或导入路径生成的 ``embedding_id`` 可能只是占位；显式调用本方法时按 provider
        规范覆盖为稳定指纹（在 ``MockEmbeddingProvider`` 下为 ``mock-emb-v1-dim*-<...>``）。

        不修改 ``chunk_metadata`` 以存放向量；若行原无 metadata 或仅有业务键，则保持不变。
        """
        if not chunks:
            return []
        texts = [ch.text for ch in chunks]
        vectors = self._provider.embed_documents(texts)
        if len(vectors) != len(chunks):
            raise RuntimeError(
                f"Embedding 返回向量数 {len(vectors)} 与切片数 {len(chunks)} 不一致"
            )
        out: list[ChunkEmbeddingResult] = []
        for ch, vec in zip(chunks, vectors, strict=True):
            eid = self._provider.embedding_id_for_text(ch.text)
            ch.embedding_id = eid
            dim = len(vec)
            out.append(
                ChunkEmbeddingResult(
                    chunk_id=ch.id,
                    embedding_id=eid,
                    vector=vec,
                    dimension=dim,
                )
            )
        self.db.flush()
        return out

    def embed_and_persist_ids_for_task(self, task_id: str) -> list[ChunkEmbeddingResult]:
        """按 ``task_id`` 查询该任务下全部 ``evidence_chunks`` 后执行 ``embed_and_persist_ids``。"""
        return self.embed_and_persist_ids(self.artifacts.list_chunks(task_id))
