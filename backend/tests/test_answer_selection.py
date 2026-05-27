"""按意图选事实测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.fact import ExtractedFactRead
from app.services.answer_selection import select_facts_for_answer
from app.services.question_intent import parse_question_intent


def _fact(
    *,
    fact_id: str,
    claim: str,
    metric_name: str,
    period: str = "2024",
) -> ExtractedFactRead:
    return ExtractedFactRead(
        id=fact_id,
        task_id="t1",
        claim=claim,
        metric_name=metric_name,
        value="100亿元",
        period=period,
        source_id="s1",
        chunk_id="c1",
        confidence=0.9,
        created_at=datetime.now(timezone.utc),
    )


def test_select_rd_facts_excludes_revenue() -> None:
    plan = parse_question_intent("近一年研发投入")
    facts = [
        _fact(
            fact_id="rd",
            claim="2025年研发投入为80亿元",
            metric_name="R&D_expenditure",
            period="2025",
        ),
        _fact(
            fact_id="rev",
            claim="2025年营业收入为1000亿元",
            metric_name="revenue",
            period="2025",
        ),
    ]
    result = select_facts_for_answer(question="近一年研发投入", facts=facts, plan=plan)
    assert len(result.primary_facts) >= 1
    assert all("研发" in f.claim or "r&d" in (f.metric_name or "").lower() for f in result.primary_facts)
