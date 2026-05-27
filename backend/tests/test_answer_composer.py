"""答案成段写作测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.fact import ExtractedFactRead
from app.services.answer_composer import compose_report_answer
from app.services.answer_selection import AnswerFactSet, select_facts_for_answer
from app.services.question_intent import parse_question_intent


def _fact(claim: str, metric: str = "R&D_expenditure", period: str = "2025") -> ExtractedFactRead:
    return ExtractedFactRead(
        id="f1",
        task_id="t1",
        claim=claim,
        metric_name=metric,
        value="80亿元",
        period=period,
        source_id="s1",
        chunk_id="c1",
        confidence=0.9,
        created_at=datetime.now(timezone.utc),
    )


def test_compose_report_answer_prose() -> None:
    question = "近一年研发投入"
    plan = parse_question_intent(question)
    fact_set = select_facts_for_answer(
        question=question,
        facts=[_fact("2025年研发投入为80亿元")],
        plan=plan,
    )
    text = compose_report_answer(
        company_name="某A股新能源上市公司",
        question=question,
        fact_set=fact_set,
        plan=plan,
    )
    assert "新能源" in text
    assert "80亿元" in text
    assert "核心发现" not in text
    assert "验证状态" not in text


def test_compose_empty_facts() -> None:
    plan = parse_question_intent("近一年研发投入")
    text = compose_report_answer(
        company_name="某A股新能源上市公司",
        question="近一年研发投入",
        fact_set=AnswerFactSet(),
        plan=plan,
    )
    assert "暂未找到" in text
