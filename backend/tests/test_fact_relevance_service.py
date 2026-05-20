from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.fact import ExtractedFactRead
from app.services.fact_relevance import FactRelevanceService


def _fact(
    *,
    fact_id: str,
    claim: str,
    metric_name: str,
    value: str = "100亿元",
    period: str = "2024",
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


def test_plain_revenue_question_does_not_promote_segment_noise() -> None:
    result = FactRelevanceService().classify(
        question="近三年营业收入和净利润变化",
        facts=[
            _fact(fact_id="rev", claim="2024年营业收入为100亿元", metric_name="revenue"),
            _fact(
                fact_id="seg",
                claim="2024年银行存款利息收入为1亿元",
                metric_name="revenue_segment:银行存款利息",
            ),
            _fact(fact_id="np", claim="2024年净利润为30亿元", metric_name="net_profit"),
        ],
    )

    assert [item.id for item in result.core_facts] == ["rev", "np"]
    assert [item.id for item in result.supporting_facts] == ["seg"]


def test_core_facts_are_ranked_and_deduped_by_metric_period_quality() -> None:
    result = FactRelevanceService().classify(
        question="近三年营业收入和净利润变化",
        facts=[
            _fact(
                fact_id="rev_large",
                claim="2025年营业收入为172054171890.91元",
                metric_name="revenue",
                value="172054171890.91元",
                period="2025",
            ),
            _fact(
                fact_id="rev_small",
                claim="2025年营业收入为172054元",
                metric_name="revenue",
                value="172054元",
                period="2025",
            ),
            _fact(
                fact_id="rev_old",
                claim="2024年营业收入为100亿元",
                metric_name="revenue",
                value="100亿元",
                period="2024",
            ),
            _fact(
                fact_id="np",
                claim="2025年净利润为80亿元",
                metric_name="net_profit",
                value="80亿元",
                period="2025",
            ),
            _fact(
                fact_id="rev_unknown",
                claim="期间未识别：营业收入为200亿元",
                metric_name="revenue",
                value="200亿元",
                period="unknown_period",
            ),
        ],
    )

    assert [item.id for item in result.core_facts] == ["rev_large", "np", "rev_old"]


def test_recent_multi_year_question_prefers_completed_annual_window() -> None:
    current_year = datetime.now(timezone.utc).year
    facts = [
        _fact(
            fact_id=f"rev_{year}",
            claim=f"{year}年营业收入为100亿元",
            metric_name="revenue",
            period=str(year),
        )
        for year in range(current_year, current_year - 5, -1)
    ]

    result = FactRelevanceService().classify(
        question="近三年营业收入变化",
        facts=facts,
    )

    assert [item.period for item in result.core_facts] == [
        str(current_year - 1),
        str(current_year - 2),
        str(current_year - 3),
    ]


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


def test_business_question_keeps_registry_admin_facts_as_supporting_context() -> None:
    result = FactRelevanceService().classify(
        question="主要业务板块",
        facts=[
            _fact(
                fact_id="date",
                claim="测试公司成立于2023年11月2日",
                metric_name="incorporation_date",
                value="2023-11-02",
                period="2023",
            ),
            _fact(
                fact_id="capital",
                claim="测试公司注册资本为10万元",
                metric_name="registered_capital",
                value="10万元",
                period="unknown_period",
            ),
            _fact(
                fact_id="industry",
                claim="测试公司所属行业为专业技术服务业",
                metric_name="industry",
                value="专业技术服务业",
                period="unknown_period",
            ),
            _fact(
                fact_id="scope",
                claim="测试公司经营范围包括软件开发、技术服务和信息系统集成服务",
                metric_name="operation_scope",
                value="软件开发；技术服务；信息系统集成服务",
                period="unknown_period",
            ),
        ],
    )

    assert [item.id for item in result.core_facts] == ["industry", "scope"]
    assert [item.id for item in result.supporting_facts] == ["date", "capital"]
    assert "business" in result.intent_labels
