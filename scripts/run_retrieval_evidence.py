"""Evaluate BM25 baseline versus the project's offline hybrid retrieval components."""

from __future__ import annotations

import json
import math
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.providers.embedding.local_hashing_provider import LocalHashingEmbeddingProvider  # noqa: E402
from app.services.rag.hybrid_retrieval import _bm25_rank  # noqa: E402
from app.services.rag.query_optimizer import QueryOptimizer  # noqa: E402
from app.services.rag.reranker import LexicalReranker  # noqa: E402
from app.services.rag.rrf import reciprocal_rank_fusion  # noqa: E402

DATASET = ROOT / "evidence" / "datasets" / "retrieval_curated_v1.json"
RAW = ROOT / "evidence" / "raw" / "retrieval_benchmark.json"
FAILURES = ROOT / "evidence" / "failures" / "retrieval_failures.json"
REPORT = ROOT / "evidence" / "reports" / "retrieval_benchmark.md"


def cosine(a: list[float], b: list[float]) -> float:
    numerator = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return numerator / (norm_a * norm_b) if norm_a and norm_b else 0.0


def dense_rank(ids: list[str], vectors: list[list[float]], query: str, provider: LocalHashingEmbeddingProvider) -> list[str]:
    query_vector = provider.embed_query(query)
    scored = [(chunk_id, cosine(query_vector, vector)) for chunk_id, vector in zip(ids, vectors, strict=True)]
    return [chunk_id for chunk_id, _ in sorted(scored, key=lambda item: item[1], reverse=True)]


def metrics(ranked: list[str], relevant: set[str], k: int) -> dict[str, float]:
    selected = ranked[:k]
    if not relevant:
        return {"recall": 1.0 if not selected else 0.0, "ndcg": 1.0 if not selected else 0.0, "mrr": 1.0 if not selected else 0.0}
    hits = [1 if chunk_id in relevant else 0 for chunk_id in selected]
    recall = sum(hits) / len(relevant)
    dcg = sum(hit / math.log2(rank + 2) for rank, hit in enumerate(hits))
    ideal = sum(1 / math.log2(rank + 2) for rank in range(min(len(relevant), k)))
    first_rank = next((rank for rank, hit in enumerate(hits, start=1) if hit), None)
    return {"recall": recall, "ndcg": dcg / ideal if ideal else 0.0, "mrr": 1 / first_rank if first_rank else 0.0}


def summarize(rows: list[dict], prefix: str, positive_count: int) -> dict:
    positives = [row for row in rows if row["relevant_count"] > 0]
    negatives = [row for row in rows if row["relevant_count"] == 0]
    return {
        "recall_at_5": statistics.mean(row[prefix]["at5"]["recall"] for row in positives),
        "recall_at_10": statistics.mean(row[prefix]["at10"]["recall"] for row in positives),
        "ndcg_at_10": statistics.mean(row[prefix]["at10"]["ndcg"] for row in positives),
        "mrr_at_10": statistics.mean(row[prefix]["at10"]["mrr"] for row in positives),
        "positive_queries": positive_count,
        "no_answer_queries": len(negatives),
        "no_answer_false_positive_rate": statistics.mean(1.0 if row[prefix]["ranked"] else 0.0 for row in negatives),
        "latency_ms": {
            "p50": statistics.median(row[prefix]["latency_ms"] for row in rows),
            "p95": sorted(row[prefix]["latency_ms"] for row in rows)[math.ceil(len(rows) * 0.95) - 1],
        },
    }


def main() -> None:
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    ids = [chunk["id"] for chunk in dataset["corpus"]]
    texts = [chunk["text"] for chunk in dataset["corpus"]]
    text_by_id = dict(zip(ids, texts, strict=True))
    provider = LocalHashingEmbeddingProvider(dimension=128)
    vectors = provider.embed_documents(texts)
    optimizer = QueryOptimizer()
    reranker = LexicalReranker()
    rows: list[dict] = []

    for item in dataset["queries"]:
        query = item["query"]
        relevant = set(item["relevant_chunk_ids"])

        started = time.perf_counter()
        baseline_ranked = _bm25_rank(ids, texts, query, top_k=10)
        baseline_latency = (time.perf_counter() - started) * 1000

        started = time.perf_counter()
        expanded = optimizer.optimize(query, enable_llm_rewrite=False)
        dense_lists = [dense_rank(ids, vectors, expanded_query, provider)[:20] for expanded_query in expanded]
        sparse_lists = [_bm25_rank(ids, texts, expanded_query, top_k=20) for expanded_query in expanded]
        fused = reciprocal_rank_fusion([*dense_lists, *sparse_lists], top_n=30)
        candidate_texts = [text_by_id[chunk_id] for chunk_id in fused]
        reranked = reranker.rerank(query, candidate_texts, top_k=10)
        current_ranked = [fused[index] for index, _ in reranked]
        current_latency = (time.perf_counter() - started) * 1000

        rows.append(
            {
                **item,
                "relevant_count": len(relevant),
                "expanded_queries": expanded,
                "baseline": {
                    "ranked": baseline_ranked,
                    "latency_ms": baseline_latency,
                    "at5": metrics(baseline_ranked, relevant, 5),
                    "at10": metrics(baseline_ranked, relevant, 10),
                },
                "current": {
                    "ranked": current_ranked,
                    "latency_ms": current_latency,
                    "at5": metrics(current_ranked, relevant, 5),
                    "at10": metrics(current_ranked, relevant, 10),
                },
            }
        )

    positive_count = sum(row["relevant_count"] > 0 for row in rows)
    summary = {
        "queries": len(rows),
        "corpus_chunks": len(ids),
        "baseline": summarize(rows, "baseline", positive_count),
        "current": summarize(rows, "current", positive_count),
    }
    summary["changes"] = {
        "recall_at_5_pp": (summary["current"]["recall_at_5"] - summary["baseline"]["recall_at_5"]) * 100,
        "ndcg_at_10_pp": (summary["current"]["ndcg_at_10"] - summary["baseline"]["ndcg_at_10"]) * 100,
    }
    artifact = {
        "schema_version": 1,
        "run_type": "offline fixture / synthetic source excerpts / human-curated labels",
        "dataset": str(DATASET.relative_to(ROOT)).replace("\\", "/"),
        "baseline": "BM25 top-10",
        "current": "LocalHashing dense + BM25 over QueryOptimizer expansions + RRF + LexicalReranker",
        "summary": summary,
        "results": rows,
    }
    failures = [
        row for row in rows
        if row["relevant_count"] == 0
        or row["current"]["at10"]["recall"] < 1.0
        or row["current"]["at10"]["recall"] < row["baseline"]["at10"]["recall"]
    ]
    for path in [RAW, FAILURES, REPORT]:
        path.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    FAILURES.write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT.write_text(
        "# Retrieval benchmark\n\n"
        f"Run type: {artifact['run_type']}.\n\n"
        f"- Corpus: {len(ids)} chunks; queries: {len(rows)} ({positive_count} positive, {len(rows)-positive_count} no-answer)\n"
        f"- BM25 Recall@5 / NDCG@10: {summary['baseline']['recall_at_5']:.3f} / {summary['baseline']['ndcg_at_10']:.3f}\n"
        f"- Hybrid Recall@5 / NDCG@10: {summary['current']['recall_at_5']:.3f} / {summary['current']['ndcg_at_10']:.3f}\n"
        f"- Change: {summary['changes']['recall_at_5_pp']:+.2f} pp Recall@5; {summary['changes']['ndcg_at_10_pp']:+.2f} pp NDCG@10\n"
        f"- No-answer false-positive rate: BM25 {summary['baseline']['no_answer_false_positive_rate']:.1%}; hybrid {summary['current']['no_answer_false_positive_rate']:.1%}\n"
        f"- Failure artifact entries: {len(failures)}\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
