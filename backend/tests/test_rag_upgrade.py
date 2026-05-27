"""升级计划 Phase 2：RAG 组件单元测试。"""

from __future__ import annotations

import pytest
from app.services.rag.hybrid_retrieval import HybridRetrievalService, _bm25_rank
from app.services.rag.query_optimizer import QueryOptimizer
from app.services.rag.reranker import LexicalReranker, build_reranker
from app.services.rag.rrf import reciprocal_rank_fusion
from sqlalchemy.orm import Session as OrmSession


class _HybridSettings:
    hybrid_dense_top_k = 50
    hybrid_sparse_top_k = 50
    hybrid_fusion_top_k = 30

    @staticmethod
    def effective(name: str) -> object:
        values = {
            "hybrid_retrieval_enabled": True,
            "hybrid_retrieval_llm_rewrite": False,
            "reranker_backend": "lexical",
        }
        return values[name]


class _RewriteProvider:
    def rewrite_retrieval_query(self, question: str) -> str:
        return f"  {question}  "


def test_rrf_merges_rankings() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], top_n=3)
    assert fused[0] == "b"
    assert set(fused) == {"a", "b", "c"}


def test_rrf_handles_non_positive_limits() -> None:
    assert reciprocal_rank_fusion([["a", "b"]], top_n=0) == []
    assert reciprocal_rank_fusion([["a"]], k=-1, top_n=1) == ["a"]


def test_query_optimizer_keywords() -> None:
    queries = QueryOptimizer().optimize("某A股上市公司2024年研发投入和营收增长情况", enable_llm_rewrite=False)
    assert "研发投入" in queries[0]
    assert len(queries) >= 2


def test_query_optimizer_deduplicates_cleaned_rewrites() -> None:
    queries = QueryOptimizer(llm_provider=_RewriteProvider()).optimize("revenue")
    assert queries == ["revenue"]


def test_query_optimizer_decomposes_complex_question_with_limits() -> None:
    question = "研发投入是多少？营业收入是多少？净利润是多少？产能情况如何？"
    queries = QueryOptimizer().optimize(question, enable_llm_rewrite=False)

    assert "研发投入是多少" in queries
    assert "营业收入是多少" in queries
    assert "净利润是多少" in queries
    assert "产能情况如何" not in queries


def test_lexical_reranker_orders_by_overlap() -> None:
    chunks = ["营收增长 10%", "无关段落", "研发投入 309 亿元"]
    ranked = LexicalReranker().rerank("研发投入", chunks, top_k=2)
    assert ranked[0][0] == 2


def test_lexical_reranker_negative_top_k_returns_empty() -> None:
    ranked = LexicalReranker().rerank("研发投入", ["研发投入 309 亿元"], top_k=-1)
    assert ranked == []


def test_build_reranker_normalizes_backend_name() -> None:
    assert isinstance(build_reranker("  lexical  "), LexicalReranker)


def test_bm25_rank_non_positive_top_k_returns_empty() -> None:
    assert _bm25_rank(["a", "b"], ["研发", "营收"], "研发", 0) == []
    assert _bm25_rank(["a", "b"], ["研发", "营收"], "研发", -1) == []


def test_hybrid_retrieval_validates_query_before_work(db: OrmSession) -> None:
    svc = HybridRetrievalService(db, settings=_HybridSettings(), reranker=LexicalReranker())

    with pytest.raises(ValueError, match="query 不能为空"):
        svc.retrieve_for_task(
            task_id="task",
            query=" \n ",
            top_k=3,
            embedding_provider=object(),
            vector_store=object(),
        )


def test_hybrid_retrieval_non_positive_top_k_returns_empty(db: OrmSession) -> None:
    svc = HybridRetrievalService(db, settings=_HybridSettings(), reranker=LexicalReranker())

    assert (
        svc.retrieve_for_task(
            task_id="task",
            query="研发",
            top_k=-1,
            embedding_provider=object(),
            vector_store=object(),
        )
        == []
    )
