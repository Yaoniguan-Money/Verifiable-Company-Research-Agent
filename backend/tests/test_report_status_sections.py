from __future__ import annotations

from datetime import datetime, timezone

from app.providers.llm import MockLLMProvider
from app.schemas.common import TaskStatus
from app.schemas.fact import ExtractedFactRead
from app.schemas.task import ResearchTaskRead


def _fact(*, fact_id: str, claim: str) -> ExtractedFactRead:
    return ExtractedFactRead(
        id=fact_id,
        task_id="task_1",
        claim=claim,
        metric_name="revenue",
        value="100",
        period="2024",
        source_id=f"source_{fact_id}",
        chunk_id=f"chunk_{fact_id}",
        confidence=0.8,
        created_at=datetime.now(timezone.utc),
    )


def test_report_keeps_outdated_and_rejected_facts_out_of_insufficient_bucket() -> None:
    now = datetime.now(timezone.utc)
    task = ResearchTaskRead(
        id="task_1",
        user_id="user_1",
        company_name="Acme",
        question="Summarize evidence quality",
        status=TaskStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )

    report = MockLLMProvider().generate_report(
        task=task,
        verified_facts=[],
        conflicted_facts=[],
        insufficient_facts=[],
        verification_results=[],
        risk_analysis="No additional risk analysis.",
        citations=[],
        outdated_facts=[_fact(fact_id="old", claim="old source fact")],
        rejected_facts=[_fact(fact_id="bad", claim="bad source fact")],
    )

    assert "status=outdated" in report.content
    assert "old source fact" in report.content
    assert "status=rejected" in report.content
    assert "bad source fact" in report.content
