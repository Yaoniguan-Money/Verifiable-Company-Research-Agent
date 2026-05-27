"""按问题意图从已验证事实中挑选用于回答的事实集合。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.metric_registry import get_metric_registry
from app.domain.report_limits import (
    MAX_CONTEXT_FACTS,
    MAX_PRIMARY_FACTS,
)
from app.schemas.fact import ExtractedFactRead
from app.services.question_intent import (
    AnswerPlan,
    fact_matches_metric_family,
    parse_question_intent,
)
from app.services.question_time_scope import ResearchTimeScope, period_year

NUMERIC_UNIT_FACTORS = (
    ("万亿", 1_000_000_000_000),
    ("亿元", 100_000_000),
    ("亿", 100_000_000),
    ("万元", 10_000),
    ("千元", 1_000),
)


@dataclass(slots=True)
class AnswerFactSet:
    """用于生成读者向正文的结构化事实子集。"""

    primary_facts: list[ExtractedFactRead] = field(default_factory=list)
    context_facts: list[ExtractedFactRead] = field(default_factory=list)
    verification_conflicted_count: int = 0
    metric_ambiguity_count: int = 0
    gap_notes: list[str] = field(default_factory=list)


def select_facts_for_answer(
    *,
    question: str,
    facts: list[ExtractedFactRead],
    plan: AnswerPlan | None = None,
    time_scope: ResearchTimeScope | None = None,
    verification_conflicted_count: int = 0,
    max_primary: int = MAX_PRIMARY_FACTS,
) -> AnswerFactSet:
    """从事实池中选出最贴合用户问题的主答事实（通常仅 verified）。"""
    plan = plan or parse_question_intent(question, time_scope=time_scope)
    scope = time_scope or plan.time_scope

    candidates = list(facts)
    if plan.strict_metrics and plan.metric_families:
        candidates = [
            f
            for f in candidates
            if fact_matches_metric_family(f.metric_name, f.claim, plan.metric_families)
        ]

    candidates = _apply_time_filter(candidates, scope, plan)
    candidates = _dedupe_by_metric_period(candidates)
    candidates = _drop_non_preferred_metrics(candidates, plan)
    candidates = _rank_for_answer(candidates, plan)

    primary = candidates[:max_primary]
    primary_ids = {p.id for p in primary}
    if plan.answer_mode.value == "trend" or not plan.metric_families:
        context = [f for f in candidates if f.id not in primary_ids][:MAX_CONTEXT_FACTS]
    else:
        context = []
    gaps = _build_gap_notes(question, plan, primary)

    return AnswerFactSet(
        primary_facts=primary,
        context_facts=context,
        verification_conflicted_count=verification_conflicted_count,
        gap_notes=gaps,
    )


def _apply_time_filter(
    facts: list[ExtractedFactRead],
    scope: ResearchTimeScope | None,
    plan: AnswerPlan,
) -> list[ExtractedFactRead]:
    if scope is None:
        return facts
    preferred = scope.preferred_years()
    if not preferred:
        return facts

    if scope.strict or scope.window_years == 1:
        in_window = [f for f in facts if _year_in_preferred(f.period, preferred)]
        if in_window:
            return in_window

    in_window = [f for f in facts if _year_in_preferred(f.period, preferred)]
    out_window = [f for f in facts if f not in in_window]
    if in_window:
        if plan.answer_mode.value == "trend" and scope.window_years and scope.window_years > 1:
            return in_window
        return in_window + out_window[:1]
    return facts


def _year_in_preferred(period: str | None, preferred: set[int]) -> bool:
    year = period_year(period)
    if year is None:
        return True
    return year in preferred


def _drop_non_preferred_metrics(
    facts: list[ExtractedFactRead], plan: AnswerPlan
) -> list[ExtractedFactRead]:
    """If a metric family's preferred metric is present, drop other metrics in the same family.

    e.g. when R&D_total_spending (634亿) exists, drop R&D_expenditure (579.78亿)
    because the user asking about 研发投入 wants the total, not just the expense line.
    """
    if not plan.metric_families:
        return facts

    if "revenue" in plan.metric_families and "revenue_structure" not in plan.metric_families:
        has_total_revenue = any(_metric_family(f) == "revenue" for f in facts)
        if has_total_revenue:
            # 普通“营业收入”问题优先总收入；分业务收入容易把利息收入等噪声带进主答案。
            facts = [f for f in facts if _metric_family(f) != "revenue_segment"]

    registry = get_metric_registry()
    preferred_by_family: dict[str, str] = {}
    for fid in plan.metric_families:
        p = registry.preferred_metric(fid)
        if p:
            preferred_by_family[fid] = p

    present_families: set[str] = set()
    present_preferred: set[str] = set()
    for f in facts:
        fam = _metric_family(f)
        present_families.add(fam)
        if f.metric_name in preferred_by_family.values():
            present_preferred.add(f.metric_name)

    if not present_preferred:
        return facts

    return [
        f for f in facts
        if f.metric_name in present_preferred
        or _metric_family(f) not in present_families
        or not any(
            p in present_preferred
            for fid, p in preferred_by_family.items()
            if _metric_family(f) == fid
        )
    ]


def _dedupe_by_metric_period(facts: list[ExtractedFactRead]) -> list[ExtractedFactRead]:
    best: dict[tuple[str, str], ExtractedFactRead] = {}
    for fact in facts:
        key = (_metric_family(fact), fact.period or "unknown")
        current = best.get(key)
        # LLM facts (confidence >= 1.0) always win over regex facts
        if current is None:
            best[key] = fact
        elif (float(fact.confidence or 0) >= 1.0) != (float(current.confidence or 0) >= 1.0):
            if float(fact.confidence or 0) >= 1.0:
                best[key] = fact
        elif _quality(fact) > _quality(current):
            best[key] = fact
    return list(best.values())


def _metric_family(fact: ExtractedFactRead) -> str:
    metric = (fact.metric_name or "").lower()
    if metric.startswith("r&d"):
        return "rd"
    if "profit" in metric:
        return "profit"
    if metric == "revenue":
        return "revenue"
    if metric.startswith("revenue_segment"):
        return "revenue_segment"
    return metric or "unknown"


def _quality(fact: ExtractedFactRead) -> float:
    period_score = 1_000_000_000 if period_year(fact.period) else 0
    return period_score + _normalized_value(fact.value) + float(fact.confidence or 0)


def _normalized_value(value: str | None) -> float:
    if not value:
        return 0.0
    match = re.search(r"\d+(?:\.\d+)?", value.replace(",", ""))
    if not match:
        return 0.0
    number = float(match.group(0))
    for unit, factor in NUMERIC_UNIT_FACTORS:
        if unit in value:
            return number * factor
    return number


def _rank_for_answer(facts: list[ExtractedFactRead], plan: AnswerPlan) -> list[ExtractedFactRead]:
    families = plan.metric_families

    def family_rank(fact: ExtractedFactRead) -> int:
        fam = _metric_family(fact)
        order = ["rd", "revenue", "profit", "revenue_segment", "capacity", "business"]
        if not families:
            return 5
        for idx, name in enumerate(order):
            if name in families and fam.startswith(name.split("_")[0]):
                return idx
        if fact_matches_metric_family(fact.metric_name, fact.claim, families):
            return 2
        return 9

    scope = plan.time_scope

    def time_key(fact: ExtractedFactRead) -> tuple[int, int]:
        year = period_year(fact.period) or 0
        if scope is None:
            return (1, -year)
        preferred = scope.preferred_years()
        if not preferred:
            return (1, -year)
        return (0 if year in preferred else 1, -year)

    return sorted(facts, key=lambda f: (
        *time_key(f),
        family_rank(f),
        # LLM facts (confidence >= 1.0) rank above regex facts
        0 if float(f.confidence or 0) >= 1.0 else 1,
        -_quality(f),
    ))


def _build_gap_notes(
    question: str,
    plan: AnswerPlan,
    primary: list[ExtractedFactRead],
) -> list[str]:
    notes: list[str] = []
    scope = plan.time_scope
    if scope is None or not scope.window_years or scope.window_years < 2:
        return notes
    preferred = scope.preferred_years()
    years_in_facts = {y for f in primary if (y := period_year(f.period)) is not None}
    missing = preferred - years_in_facts
    if missing and years_in_facts:
        missing_label = "、".join(f"{y}年" for y in sorted(missing, reverse=True))
        notes.append(
            f"材料中尚未同时给出{missing_label}的可核对数据，"
            f"暂无法完整描述近{scope.window_years}年的连续变化。"
        )
    if plan.metric_families and "rd" in plan.metric_families:
        if not any(_metric_family(f) == "rd" for f in primary):
            notes.append("本次未抽到与研发相关的可核对数字。")
    return notes
