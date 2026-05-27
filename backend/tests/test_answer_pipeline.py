from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.fact import ExtractedFactRead
from app.schemas.verification import VerificationResultRead
from app.services.answer_pipeline import AnswerPipeline


def _fact(
    *,
    fact_id: str,
    claim: str,
    metric_name: str,
    value: str = "100亿元",
    period: str = "2025",
) -> ExtractedFactRead:
    return ExtractedFactRead(
        id=fact_id,
        task_id="task_1",
        claim=claim,
        metric_name=metric_name,
        value=value,
        period=period,
        source_id=f"source_{fact_id}",
        chunk_id=f"chunk_{fact_id}",
        confidence=0.8,
        created_at=datetime.now(timezone.utc),
    )


def _verification(fact_id: str, status: str) -> VerificationResultRead:
    return VerificationResultRead(
        id=f"v_{fact_id}",
        fact_id=fact_id,
        task_id="task_1",
        status=status,
        confidence=0.8,
        supporting_sources=[f"source_{fact_id}"],
        conflicting_sources=["source_other"] if status == "conflicted" else [],
        reason="test reason",
        reason_code="test",
        created_at=datetime.now(timezone.utc),
    )


def test_pipeline_keeps_optional_context_empty_for_strict_metric_question() -> None:
    rd = _fact(fact_id="rd", claim="2025年研发投入为100亿元", metric_name="R&D_expenditure")
    revenue = _fact(fact_id="rev", claim="2025年营业收入为200亿元", metric_name="revenue")

    ctx = AnswerPipeline().build_context(
        company_name="Test Co",
        question="2025年研发投入是多少？",
        verified_facts=[rd, revenue],
        verifications=[_verification("rd", "verified"), _verification("rev", "verified")],
    )

    assert [fact.id for fact in ctx.primary_facts] == ["rd"]
    assert ctx.optional_context_facts == []


def test_pipeline_reports_metric_ambiguity_for_conflicted_values() -> None:
    f1 = _fact(fact_id="f1", claim="2025年研发投入为100亿元", metric_name="R&D_expenditure")
    f2 = _fact(
        fact_id="f2",
        claim="2025年研发投入为120亿元",
        metric_name="R&D_expenditure",
        value="120亿元",
    )

    ctx = AnswerPipeline().build_context(
        company_name="Test Co",
        question="2025年研发投入是多少？",
        verified_facts=[],
        conflicted_facts=[f1, f2],
        verifications=[_verification("f1", "conflicted"), _verification("f2", "conflicted")],
    )

    assert len(ctx.ambiguities) == 1
    assert len(ctx.ambiguities[0].values) == 2

