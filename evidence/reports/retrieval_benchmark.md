# Retrieval benchmark

Run type: offline fixture / synthetic source excerpts / human-curated labels.

- Corpus: 51 chunks; queries: 57 (52 positive, 5 no-answer)
- BM25 Recall@5 / NDCG@10: 0.904 / 0.801
- Hybrid Recall@5 / NDCG@10: 0.952 / 0.850
- Change: +4.81 pp Recall@5; +4.91 pp NDCG@10
- No-answer false-positive rate: BM25 100.0%; hybrid 100.0%
- Failure artifact entries: 6
