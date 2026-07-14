# Coverage evidence

Command: `python -m coverage run --branch --data-file=evidence/raw/.coverage -m pytest backend/tests -q -p no:cacheprovider`

2026-07-14 results, 450 passing tests:

| Module | Statements | Branches |
|---|---:|---:|
| `fact_extraction.py` | 90.57% | 73.68% |
| `fact_verification.py` | 78.54% | 70.00% |
| `fact_value_normalization.py` | 87.04% | 72.22% |
| `fact_metric_normalization.py` | 96.43% | 83.33% |
| `report_grounding.py` | 96.36% | 88.89% |
| `hybrid_retrieval.py` | 45.54% | 20.00% |
| `rrf.py` | 100.00% | 100.00% |
| Whole backend test scope | 87.31% | 65.90% |

The low hybrid-retrieval branch coverage is retained as a gap and must not be hidden by citing only RRF or grounding coverage.
