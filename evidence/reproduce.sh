#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export PYTHONPATH=backend
python scripts/build_retrieval_evidence_dataset.py
python scripts/build_fact_evidence_dataset.py
python scripts/run_retrieval_evidence.py
python scripts/run_fact_extraction_evidence.py
python -m coverage run --branch --data-file=evidence/raw/.coverage -m pytest backend/tests -q -p no:cacheprovider --junitxml=evidence/raw/pytest.xml
python -m coverage json --data-file=evidence/raw/.coverage -o evidence/raw/coverage.json
python scripts/collect_evidence_environment.py
