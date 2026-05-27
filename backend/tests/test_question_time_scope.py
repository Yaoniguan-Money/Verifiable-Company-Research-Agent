"""研究问题时间范围解析测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.question_time_scope import (
    ResearchTimeScope,
    fact_time_scope_rank_key,
    parse_research_time_scope,
)


def test_parse_near_one_year_variants() -> None:
    for question in ("近一年的利润", "近一年利润", "过去一年净利润", "去年利润"):
        scope = parse_research_time_scope(question)
        assert scope is not None
        assert scope.window_years == 1
        assert scope.strict is False


def test_parse_near_three_years() -> None:
    scope = parse_research_time_scope("近三年研发投入")
    assert scope is not None
    assert scope.window_years == 3


def test_strict_when_user_says_only_one_year() -> None:
    scope = parse_research_time_scope("仅看近一年净利润")
    assert scope is not None
    assert scope.strict is True


def test_explicit_year_without_compare_is_strict() -> None:
    scope = parse_research_time_scope("2024年净利润是多少")
    assert scope is not None
    assert scope.explicit_years == frozenset({2024})
    assert scope.strict is True


def test_explicit_year_with_compare_is_soft() -> None:
    scope = parse_research_time_scope("2023与2024年净利润对比")
    assert scope is not None
    assert scope.explicit_years == frozenset({2023, 2024})
    assert scope.strict is False


def test_preferred_report_years_for_one_year_window() -> None:
    scope = parse_research_time_scope("近一年利润")
    assert scope is not None
    years = scope.preferred_years(now=datetime(2026, 5, 26, tzinfo=timezone.utc))
    assert years == {2025}


def test_soft_rank_key_prefers_matching_year() -> None:
    scope = ResearchTimeScope(window_years=1, strict=False)
    assert fact_time_scope_rank_key("2025", scope) < fact_time_scope_rank_key("2022", scope)


def test_unspecified_question_returns_none() -> None:
    assert parse_research_time_scope("公司主要业务是什么") is None
