"""从研究问题解析用户意图与答题计划。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.domain.metric_registry import get_metric_registry
from app.services.question_time_scope import ResearchTimeScope, parse_research_time_scope


class AnswerMode(str, Enum):
    """回答组织方式。"""

    DIRECT = "direct_answer"
    TREND = "trend"
    LIST = "list_facts"


@dataclass(frozen=True, slots=True)
class AnswerPlan:
    """面向答题流水线的问题理解结果。"""

    metric_families: frozenset[str]
    time_scope: ResearchTimeScope | None
    answer_mode: AnswerMode
    strict_metrics: bool
    """为 True 时只保留与 metric_families 强匹配的事实。"""

    @property
    def intent_labels(self) -> list[str]:
        return sorted(self.metric_families) if self.metric_families else ["general"]


def detect_metric_families(question: str) -> frozenset[str]:
    """指标族检测统一走 MetricRegistry。"""
    return get_metric_registry().detect_families(question)


def detect_answer_mode(question: str, metric_families: frozenset[str]) -> AnswerMode:
    q = question or ""
    if re.search(r"(对比|比较|变化|趋势|逐年|历年|各年|多年|同比|环比)", q):
        return AnswerMode.TREND
    if re.search(r"(有哪些|列举|分别|构成|结构)", q) and metric_families:
        return AnswerMode.LIST
    return AnswerMode.DIRECT


def parse_question_intent(
    question: str,
    *,
    time_scope: ResearchTimeScope | None = None,
) -> AnswerPlan:
    """规则解析问题意图；时间范围可外部注入（如 LLM 增强后的 scope）。"""
    families = detect_metric_families(question)
    scope = time_scope or parse_research_time_scope(question)
    mode = detect_answer_mode(question, families)
    strict = bool(families) and not re.search(
        r"(概况|概览|全面|整体|综合|各方面)",
        question or "",
    )
    if scope and scope.strict:
        strict = True
    return AnswerPlan(
        metric_families=families,
        time_scope=scope,
        answer_mode=mode,
        strict_metrics=strict,
    )


def fact_matches_metric_family(
    fact_metric: str | None,
    claim: str,
    families: frozenset[str],
) -> bool:
    """判断事实是否属于目标指标族之一。"""
    if not families:
        return True
    return get_metric_registry().matches_family(
        metric_name=fact_metric,
        claim=claim,
        family_ids=families,
    )
