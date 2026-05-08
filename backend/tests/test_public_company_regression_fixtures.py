from __future__ import annotations

import json
import re
from pathlib import Path

from app.evaluation import score_public_regression_case, score_public_regression_suite
from app.schemas.retrieval import RetrievedEvidence
from app.services.fact_extraction import FactExtractionService

REGRESSION_FILE = Path("data/eval/public_company_regression.json")
FIXTURE_FILE = Path("data/eval/public_company_regression_fixtures.json")


def test_public_company_fixtures_cover_expected_metric_groups() -> None:
    regression = json.loads(REGRESSION_FILE.read_text(encoding="utf-8"))
    fixture = json.loads(FIXTURE_FILE.read_text(encoding="utf-8"))
    fixtures_by_company = {case["company_name"]: case for case in fixture["cases"]}
    scores = []

    for case in regression["cases"]:
        company = case["company_name"]
        fixture_case = fixtures_by_company[company]
        assert all(
            len(set(re.findall(r"20\d{2}年", source["raw_content"]))) >= 2
            for source in fixture_case["sources"]
        )
        evidences = [
            RetrievedEvidence(
                chunk_id=f"fixture_chunk_{idx}",
                source_id=f"fixture_source_{idx}",
                task_id="fixture_regression",
                text=source["raw_content"],
                score=1.0,
                source_title=source["title"],
                source_url=source["url"],
                source_type=source["source_type"],
                retrieved_at=source["retrieved_at"],
                metadata=None,
            )
            for idx, source in enumerate(fixture_case["sources"])
        ]
        facts = FactExtractionService().extract_from_retrieved_evidences(
            task_id="fixture_regression",
            company_name=company,
            question=case["question"],
            evidences=evidences,
        ).facts
        metric_groups = sorted({(fact.metric_name or "").split(":", 1)[0] for fact in facts})
        scores.append(
            score_public_regression_case(
                company_name=company,
                expected_metric_groups=case["expected_metric_groups"],
                observed_metric_groups=metric_groups,
                source_count=len(evidences),
                fact_count=len(facts),
                minimum_coverage_ratio=0.7,
            )
        )

    suite = score_public_regression_suite(scores)

    assert suite.passed
    assert suite.average_metric_coverage_ratio >= 0.9
