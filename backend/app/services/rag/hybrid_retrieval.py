"""混合检索：Dense + BM25 + RRF + Rerank。"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.providers.embedding.base import EmbeddingProvider
from app.providers.llm.base import LLMProvider
from app.repositories import ResearchArtifactRepository
from app.schemas.retrieval import RetrievedEvidence
from app.services.rag.query_optimizer import QueryOptimizer
from app.services.rag.reranker import Reranker, build_reranker
from app.services.rag.rrf import reciprocal_rank_fusion
from app.services.retrieval import RetrievalService
from app.vectorstores.base import VectorStore

logger = logging.getLogger(__name__)

_bm25_corpus_cache: dict[str, tuple[list[list[str]], object]] = {}


def _bm25_rank(chunk_ids: list[str], texts: list[str], query: str, top_k: int) -> list[str]:
    if top_k <= 0:
        return []
    try:
        from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]
    except ImportError:
        return chunk_ids[:top_k]

    from app.services.rag.query_optimizer import _tokenize

    # 加分隔符，避免 ["ab", "c"] 和 ["a", "bc"] 生成同一个缓存键。
    text_hash = hashlib.sha256("\0".join(texts).encode()).hexdigest()[:16]
    settings = get_settings()
    max_cache = settings.bm25_cache_max_size

    if text_hash in _bm25_corpus_cache:
        corpus, bm25 = _bm25_corpus_cache[text_hash]
    else:
        corpus = [_tokenize(text) for text in texts]
        if not corpus:
            return []
        bm25 = BM25Okapi(corpus)
        if len(_bm25_corpus_cache) >= max_cache:
            oldest = next(iter(_bm25_corpus_cache))
            del _bm25_corpus_cache[oldest]
        _bm25_corpus_cache[text_hash] = (corpus, bm25)

    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(range(len(chunk_ids)), key=lambda i: scores[i], reverse=True)
    return [chunk_ids[i] for i in ranked[:top_k]]


@dataclass
class RetrievalMetrics:
    task_id: str
    query: str
    expanded_queries: list[str] = field(default_factory=list)
    dense_hits_per_query: list[int] = field(default_factory=list)
    sparse_hits_per_query: list[int] = field(default_factory=list)
    fusion_candidates: int = 0
    rerank_candidates: int = 0
    final_results: int = 0
    duration_ms: float = 0.0
    official_fallback_added: int = 0


class HybridRetrievalService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
        llm_provider: LLMProvider | None = None,
        reranker: Reranker | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.artifacts = ResearchArtifactRepository(db)
        self.base = RetrievalService(db)
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.query_optimizer = QueryOptimizer(llm_provider)
        self.reranker = reranker or build_reranker(
            self.settings.effective("reranker_backend"),
            embedding_provider=self.embedding_provider,
        )

    def retrieve_for_task(
        self,
        *,
        task_id: str,
        query: str,
        top_k: int,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ) -> list[RetrievedEvidence]:
        query = query.strip()
        if not query:
            raise ValueError("query 不能为空或仅空白")
        if top_k <= 0:
            return []

        if not self.settings.effective("hybrid_retrieval_enabled"):
            return self.base.retrieve_for_task(
                task_id=task_id,
                query=query,
                top_k=top_k,
                embedding_provider=embedding_provider,
                vector_store=vector_store,
            )

        _t0 = time.time()
        dense_lists: list[list[str]] = []
        sparse_lists: list[list[str]] = []
        chunk_rows = self.artifacts.list_chunks(task_id)
        if not chunk_rows:
            return []

        chunk_ids = [row.id for row in chunk_rows]
        chunk_texts = [row.text for row in chunk_rows]
        chunk_map = {row.id: row for row in chunk_rows}

        queries = self.query_optimizer.optimize(
            query,
            enable_llm_rewrite=self.settings.effective("hybrid_retrieval_llm_rewrite"),
        )
        dense_k = max(self.settings.hybrid_dense_top_k, top_k)
        sparse_k = max(self.settings.hybrid_sparse_top_k, top_k)

        for q in queries:
            dense_hits = self.base.retrieve_for_task(
                task_id=task_id,
                query=q,
                top_k=dense_k,
                embedding_provider=embedding_provider,
                vector_store=vector_store,
            )
            dense_lists.append([item.chunk_id for item in dense_hits])
            sparse_lists.append(_bm25_rank(chunk_ids, chunk_texts, q, sparse_k))

        fused_ids = reciprocal_rank_fusion(
            [*dense_lists, *sparse_lists],
            top_n=self.settings.hybrid_fusion_top_k,
        )
        if not fused_ids:
            return []

        rerank_texts = [chunk_map[cid].text for cid in fused_ids if cid in chunk_map]
        reranked = self.reranker.rerank(query, rerank_texts, top_k=top_k)
        ordered_ids = [fused_ids[idx] for idx, _ in reranked if idx < len(fused_ids)]

        source_map = self.artifacts.source_map(task_id)
        out: list[RetrievedEvidence] = []
        for rank_idx, chunk_id in enumerate(ordered_ids):
            ch = chunk_map.get(chunk_id)
            if ch is None:
                continue
            src = source_map.get(ch.source_id)
            if src is None:
                continue
            score = float(top_k - rank_idx)
            for ri, rs in reranked:
                if ri < len(fused_ids) and fused_ids[ri] == chunk_id:
                    score = round(rs, 4)
                    break
            out.append(
                RetrievedEvidence(
                    chunk_id=ch.id,
                    source_id=ch.source_id,
                    task_id=ch.task_id,
                    text=ch.text,
                    score=score,
                    source_title=src.title,
                    source_url=src.url,
                    source_type=str(src.source_type),
                    retrieved_at=src.retrieved_at,
                    metadata=ch.chunk_metadata or {},
                )
            )

        metrics = RetrievalMetrics(
            task_id=task_id,
            query=query,
            expanded_queries=queries,
            dense_hits_per_query=[len(d) for d in dense_lists],
            sparse_hits_per_query=[len(s) for s in sparse_lists],
            fusion_candidates=len(fused_ids),
            rerank_candidates=len(reranked),
            final_results=len(out[:top_k]),
            duration_ms=(time.time() - _t0) * 1000,
        )
        logger.info("Retrieval completed: %s", metrics)
        return out[:top_k]
