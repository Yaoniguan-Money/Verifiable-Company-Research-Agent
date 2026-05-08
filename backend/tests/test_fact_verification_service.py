"""阶段 3.D：FactVerificationService 测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.common import SOURCE_LAYER_METADATA_KEY, SourceLayer
from app.schemas.fact import ExtractedFactRead
from app.services.fact_verification import FactVerificationService


def _fact(
    *,
    fact_id: str,
    task_id: str,
    metric_name: str,
    period: str,
    value: str,
    source_id: str,
) -> ExtractedFactRead:
    return ExtractedFactRead(
        id=fact_id,
        task_id=task_id,
        claim=f"{period} {metric_name} = {value}",
        metric_name=metric_name,
        value=value,
        period=period,
        source_id=source_id,
        chunk_id=f"chunk_{fact_id}",
        confidence=0.8,
        created_at=datetime.now(timezone.utc),
    )


def test_same_metric_period_value_multi_source_should_be_verified() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="revenue",
            period="2023",
            value="100亿元",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="revenue",
            period="2023",
            value="100 亿元",
            source_id="s2",
        ),
    ]
    out = svc.verify_facts(task_id="task_1", facts=facts)
    assert len(out.results) == 2
    assert all(r.status.value == "verified" for r in out.results)
    assert all(r.supporting_sources for r in out.results)
    assert all(r.reason for r in out.results)
    assert all(0 <= r.confidence <= 1 for r in out.results)


def test_equivalent_money_units_should_be_verified() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="R&D_expenditure",
            period="2024",
            value="542\u4ebf\u5143",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="R&D_expenditure",
            period="2024",
            value="54200000\u5343\u5143",
            source_id="s2",
        ),
    ]

    out = svc.verify_facts(task_id="task_1", facts=facts)

    assert len(out.results) == 2
    assert all(r.status.value == "verified" for r in out.results)
    assert {r.reason_code for r in out.results} == {"unit_normalized_match"}


def test_equivalent_metric_aliases_should_be_verified() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="R&D_expenditure",
            period="2024",
            value="542\u4ebf\u5143",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="r_and_d",
            period="2024",
            value="54200000\u5343\u5143",
            source_id="s2",
        ),
    ]

    out = svc.verify_facts(task_id="task_1", facts=facts)

    assert len(out.results) == 2
    assert all(r.status.value == "verified" for r in out.results)
    assert {r.reason_code for r in out.results} == {"metric_and_unit_normalized_match"}


def test_equivalent_quantity_units_should_be_verified() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="sales_volume",
            period="2024",
            value="4,479,392\u8f86",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="sales_volume",
            period="2024",
            value="447.9392\u4e07\u8f86",
            source_id="s2",
        ),
    ]

    out = svc.verify_facts(task_id="task_1", facts=facts)

    assert len(out.results) == 2
    assert all(r.status.value == "verified" for r in out.results)
    assert {r.reason_code for r in out.results} == {"unit_normalized_match"}


def test_same_metric_period_but_different_value_should_be_conflicted() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="net_profit",
            period="2023",
            value="20亿元",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="net_profit",
            period="2023",
            value="25亿元",
            source_id="s2",
        ),
    ]
    out = svc.verify_facts(task_id="task_1", facts=facts)
    assert len(out.results) == 2
    assert all(r.status.value == "conflicted" for r in out.results)
    assert {r.reason_code for r in out.results} == {"different_value_multi_source"}
    assert all(r.conflicting_sources for r in out.results)
    assert all(r.reason for r in out.results)


def test_single_source_fact_should_be_insufficient_not_verified() -> None:
    svc = FactVerificationService()
    out = svc.verify_facts(
        task_id="task_1",
        facts=[
            _fact(
                fact_id="f1",
                task_id="task_1",
                metric_name="r_and_d",
                period="2023",
                value="10亿元",
                source_id="s1",
            )
        ],
    )
    assert len(out.results) == 1
    result = out.results[0]
    assert result.status.value == "insufficient"
    assert result.reason
    assert result.reason_code == "single_source_only"
    assert result.status.value != "verified"


def test_official_entry_page_only_should_not_be_verified() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="revenue",
            period="2024",
            value="100亿元",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="revenue",
            period="2024",
            value="100亿元",
            source_id="s2",
        ),
    ]

    out = svc.verify_facts(
        task_id="task_1",
        facts=facts,
        source_context={
            "s1": (None, 0.96, {SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_ENTRY_PAGE.value}),
            "s2": (None, 0.96, {SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_ENTRY_PAGE.value}),
        },
    )

    assert all(r.status.value == "insufficient" for r in out.results)
    assert {r.reason_code for r in out.results} == {"official_entry_page_only"}


def test_low_authority_source_should_not_be_verified() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="revenue",
            period="2024",
            value="100亿元",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="revenue",
            period="2024",
            value="100亿元",
            source_id="s2",
        ),
    ]

    out = svc.verify_facts(
        task_id="task_1",
        facts=facts,
        source_context={
            "s1": (None, 0.46, {SOURCE_LAYER_METADATA_KEY: SourceLayer.THIRD_PARTY_BACKGROUND.value}),
            "s2": (None, 0.98, {SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value}),
        },
    )

    assert all(r.status.value == "insufficient" for r in out.results)
    assert {r.reason_code for r in out.results} == {"low_authority_source_not_verified"}


def test_different_period_should_not_conflict_with_each_other() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="revenue",
            period="2022",
            value="80亿元",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="revenue",
            period="2023",
            value="100亿元",
            source_id="s2",
        ),
    ]
    out = svc.verify_facts(task_id="task_1", facts=facts)
    assert all(r.status.value == "insufficient" for r in out.results)


def test_different_metric_should_not_conflict_with_each_other() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="revenue",
            period="2023",
            value="100亿元",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="net_profit",
            period="2023",
            value="20亿元",
            source_id="s2",
        ),
    ]
    out = svc.verify_facts(task_id="task_1", facts=facts)
    assert all(r.status.value == "insufficient" for r in out.results)


def test_different_profit_metrics_should_not_conflict_with_each_other() -> None:
    svc = FactVerificationService()
    facts = [
        _fact(
            fact_id="f1",
            task_id="task_1",
            metric_name="net_profit_parent",
            period="2024",
            value="136.31亿元",
            source_id="s1",
        ),
        _fact(
            fact_id="f2",
            task_id="task_1",
            metric_name="net_profit_deducted",
            period="2024",
            value="123.15亿元",
            source_id="s2",
        ),
        _fact(
            fact_id="f3",
            task_id="task_1",
            metric_name="net_profit",
            period="2024",
            value="66亿元",
            source_id="s3",
        ),
    ]

    out = svc.verify_facts(task_id="task_1", facts=facts)

    assert all(r.status.value == "insufficient" for r in out.results)


def test_no_real_llm_dependency_path() -> None:
    svc = FactVerificationService()
    out = svc.verify_facts(task_id="task_1", facts=[])
    assert out.results == []


def test_traceability_fields_always_present() -> None:
    svc = FactVerificationService()
    out = svc.verify_facts(
        task_id="task_1",
        facts=[
            _fact(
                fact_id="f1",
                task_id="task_1",
                metric_name="revenue",
                period="2023",
                value="100亿元",
                source_id="s1",
            ),
            _fact(
                fact_id="f2",
                task_id="task_1",
                metric_name="revenue",
                period="2023",
                value="110亿元",
                source_id="s2",
            ),
        ],
    )
    for r in out.results:
        assert r.fact_id
        assert r.task_id == "task_1"
        assert r.reason
        assert 0 <= r.confidence <= 1


def test_outdated_should_be_detected_by_old_period() -> None:
    svc = FactVerificationService()
    old_year = str(datetime.now(timezone.utc).year - 6)
    out = svc.verify_facts(
        task_id="task_1",
        facts=[
            _fact(
                fact_id="f_old",
                task_id="task_1",
                metric_name="revenue",
                period=old_year,
                value="100亿元",
                source_id="s_old",
            )
        ],
    )
    assert len(out.results) == 1
    assert out.results[0].status.value == "outdated"
    assert out.results[0].reason_code == "outdated_period_or_source"


def test_rejected_should_be_detected_by_invalid_value() -> None:
    svc = FactVerificationService()
    out = svc.verify_facts(
        task_id="task_1",
        facts=[
            _fact(
                fact_id="f_bad",
                task_id="task_1",
                metric_name="revenue",
                period="2024",
                value="0亿元",
                source_id="s1",
            )
        ],
    )
    assert len(out.results) == 1
    assert out.results[0].status.value == "rejected"
    assert out.results[0].reason_code == "invalid_numeric_value"


def test_all_five_statuses_are_executable() -> None:
    svc = FactVerificationService()
    old_year = str(datetime.now(timezone.utc).year - 6)
    facts = [
        _fact(fact_id="v1", task_id="task_1", metric_name="rev", period="2024", value="10亿元", source_id="s1"),
        _fact(fact_id="v2", task_id="task_1", metric_name="rev", period="2024", value="10亿元", source_id="s2"),
        _fact(fact_id="c1", task_id="task_1", metric_name="np", period="2024", value="1亿元", source_id="s3"),
        _fact(fact_id="c2", task_id="task_1", metric_name="np", period="2024", value="2亿元", source_id="s4"),
        _fact(fact_id="i1", task_id="task_1", metric_name="rd", period="2024", value="5亿元", source_id="s5"),
        _fact(fact_id="o1", task_id="task_1", metric_name="old", period=old_year, value="5亿元", source_id="s6"),
        _fact(fact_id="r1", task_id="task_1", metric_name="bad", period="2024", value="0亿元", source_id="s7"),
    ]
    out = svc.verify_facts(task_id="task_1", facts=facts)
    statuses = {r.status.value for r in out.results}
    assert {"verified", "conflicted", "insufficient", "outdated", "rejected"} <= statuses

