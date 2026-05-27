"""Query-to-evidence retrieval service."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.providers.embedding.base import EmbeddingProvider
from app.repositories import ResearchArtifactRepository
from app.schemas.common import SOURCE_CREDIBILITY_SCORE_METADATA_KEY, SOURCE_METADATA_KEY
from app.schemas.retrieval import RetrievedEvidence
from app.vectorstores.base import VectorStore


class RetrievalService:
    """将 query 编排为证据检索结果。

    仅返回 ``RetrievedEvidence``，不生成报告、不生成回答。
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.artifacts = ResearchArtifactRepository(db)

    def retrieve_for_task(
        self,
        *,
        task_id: str,
        query: str,
        top_k: int,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> list[RetrievedEvidence]:
        q = query.strip()
        if not q:
            raise ValueError("query 不能为空或仅空白")
        if top_k <= 0:
            return []

        query_embedding = embedding_provider.embed_query(q)
        hits = vector_store.similarity_search(query_embedding, top_k=top_k, task_id=task_id)
        if not hits:
            return []

        chunk_ids = [h.chunk_id for h in hits]
        chunk_rows = self.artifacts.list_chunks_by_ids(task_id=task_id, chunk_ids=chunk_ids)
        if not chunk_rows:
            return []
        chunk_map = {r.id: r for r in chunk_rows}

        source_ids = sorted({r.source_id for r in chunk_rows})
        source_rows = self.artifacts.list_sources_by_ids(source_ids)
        source_map = {s.id: s for s in source_rows}

        out: list[RetrievedEvidence] = []
        for hit in hits:
            ch = chunk_map.get(hit.chunk_id)
            if ch is None:
                # 向量库有但 DB 已不存在：跳过（2.D 可控退化）
                continue
            src = source_map.get(ch.source_id)
            if src is None:
                # source 被删除或不可见时同样跳过，避免返回不完整证据
                continue
            out.append(
                RetrievedEvidence(
                    chunk_id=ch.id,
                    source_id=ch.source_id,
                    task_id=ch.task_id,
                    text=ch.text,
                    score=hit.score,
                    source_title=src.title,
                    source_url=src.url,
                    source_type=str(src.source_type),
                    retrieved_at=src.retrieved_at,
                    metadata={
                        **(ch.chunk_metadata or {}),
                        SOURCE_CREDIBILITY_SCORE_METADATA_KEY: src.credibility_score,
                        SOURCE_METADATA_KEY: src.source_metadata or {},
                    },
                )
            )
        return out
