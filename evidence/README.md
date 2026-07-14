# Evidence package: Verifiable Company Research Agent

## Admission decisions

### A-level retrieval metric

On a frozen corpus of 51 synthetic financial-report chunks and 57 manually labeled queries (52 positive, 5 no-answer), the offline hybrid path improved Recall@5 from **90.38% to 95.19%** and NDCG@10 from **80.08% to 85.00%** versus BM25, gains of **+4.81** and **+4.91 percentage points**. The cost was higher local P50 latency (0.12ms → 2.15ms). Both methods returned false positives for all five no-answer queries; those failures remain in `failures/retrieval_failures.json`.

This is synthetic offline evidence, not live search quality or current public-company data.

### A-level fact-extraction metric

On 51 frozen annotated samples containing 131 expected facts, table-aware extraction achieved micro Precision/Recall/F1 **100.00% / 93.89% / 96.85%**, versus **100.00% / 34.35% / 51.14%** for a simple one-fact regex baseline. All 8 false negatives and zero false positives are retained; six negative risk rows produced zero false positives.

The match key is `(metric family, period, unit-normalized value)`. Dimension wording and real-filing generalization are not scored.

### B-level engineering evidence

- The legacy evaluator no longer returns hard-coded 0.82/0.78/0.80 scores when a dataset is absent. Missing and empty datasets now fail closed, and template-generated developer data is written outside the canonical eval directory with an explicit warning.
- The full backend suite passes 450 tests. Whole backend test-scope coverage is 87.31% statements / 65.90% branches; `report_grounding.py` is 96.36% / 88.89%. `hybrid_retrieval.py` remains only 45.54% / 20.00%, a recorded gap.

## Artifacts

- Config: `experiment-config.json`
- Dataset manifest: `dataset-manifest.json`
- Frozen datasets: `datasets/`
- Raw retrieval/fact/coverage/pytest/environment outputs: `raw/`
- Failure samples: `failures/`
- Reports: `reports/`
- One-command reproduction: `reproduce.ps1` or `reproduce.sh`

## Reproduction

```powershell
powershell -ExecutionPolicy Bypass -File evidence/reproduce.ps1
```

This path is offline and does not use LLM/search credentials.

## Limitations and interview answers

**Are these real annual reports?** No. The excerpts are synthetic regression fixtures that resemble table disclosures. The labels are independent of retrieval code, but the result must not be called real-world search quality.

**Why is the retrieval result still useful?** It is a paired ablation on the same 57 frozen queries, proving that the implemented hybrid components improve ranking quality over BM25 under this controlled scope. It also exposes the unresolved 100% no-answer false-positive rate.

**Why is fact F1 high?** The dataset uses structured table-style excerpts that the table extractor is designed for. The eight retained false negatives show remaining unsupported layouts. The claim does not generalize to arbitrary filings, OCR, or live LLM extraction.

**What did fail-closed evaluation fix?** Previously a missing dataset returned a plausible score. Now absence or an empty item list raises, preventing a report from passing without samples.
