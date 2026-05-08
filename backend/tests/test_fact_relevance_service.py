from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.fact import ExtractedFactRead
from app.services.fact_relevance import FactRelevanceService


def _fact(*, fact_id: str, claim: str, metric_name: str) -> ExtractedFactRead:
    return ExtractedFactRead(
        id=fact_id,
        task_id="task_1",
        claim=claim,
        metric_name=metric_name,
        value="100亿元",
        period="2024",
        source_id=f"source_{fact_id}",
        chunk_id=f"chunk_{fact_id}",
        confidence=0.8,
        created_at=datetime.now(timezone.utc),
    )


def test_rd_question_prioritizes_rd_facts_over_revenue() -> None:
    result = FactRelevanceService().classify(
        question="近三年研发投入变化和经营风险",
        facts=[
            _fact(fact_id="rd", claim="2024年研发投入为100亿元", metric_name="R&D_expenditure"),
            _fact(fact_id="rev", claim="2024年营业收入为100亿元", metric_name="revenue"),
        ],
    )

    assert [item.id for item in result.core_facts] == ["rd"]
    assert [item.id for item in result.supporting_facts] == ["rev"]
    assert "rd" in result.intent_labels


def test_revenue_structure_question_prioritizes_segment_facts() -> None:
    result = FactRelevanceService().classify(
        question="近三年研发投入和收入结构变化",
        facts=[
            _fact(fact_id="seg", claim="药品收入为100亿元", metric_name="revenue_segment:药品"),
            _fact(fact_id="np", claim="净利润为100亿元", metric_name="net_profit"),
        ],
    )

    assert [item.id for item in result.core_facts] == ["seg"]
    assert [item.id for item in result.supporting_facts] == ["np"]


def test_capacity_question_prioritizes_capacity_production_and_sales() -> None:
    result = FactRelevanceService().classify(
        question="研发投入、产能扩张和风险",
        facts=[
            _fact(fact_id="cap", claim="产能为100万辆", metric_name="production_capacity:乘用车"),
            _fact(fact_id="sales", claim="销量为100万辆", metric_name="sales_volume:乘用车"),
            _fact(fact_id="rev", claim="营业收入为100亿元", metric_name="revenue"),
        ],
    )

    assert {item.id for item in result.core_facts} == {"cap", "sales"}
    assert [item.id for item in result.supporting_facts] == ["rev"]
