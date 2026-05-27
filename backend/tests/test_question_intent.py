"""问题意图解析测试。"""

from __future__ import annotations

from app.services.question_intent import AnswerMode, detect_metric_families, parse_question_intent


def test_detect_rd_intent() -> None:
    families = detect_metric_families("某A股上市公司近一年研发投入")
    assert "rd" in families


def test_parse_direct_answer_plan() -> None:
    plan = parse_question_intent("近一年研发投入是多少")
    assert "rd" in plan.metric_families
    assert plan.answer_mode == AnswerMode.DIRECT
    assert plan.time_scope is not None
    assert plan.time_scope.window_years == 1


def test_parse_trend_mode() -> None:
    plan = parse_question_intent("近三年研发投入变化")
    assert plan.answer_mode == AnswerMode.TREND
    assert plan.time_scope is not None
    assert plan.time_scope.window_years == 3
