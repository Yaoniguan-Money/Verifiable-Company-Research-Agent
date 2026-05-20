"""Question-aware fact relevance scoring for report assembly."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas.fact import ExtractedFactRead

INTENT_KEYWORDS = {
    "rd": ("研发", "r&d", "rd", "research"),
    "revenue_structure": ("收入结构", "营收结构", "分业务", "业务结构", "收入构成"),
    "revenue": ("收入", "营收", "营业收入", "revenue"),
    "capacity": ("产能", "扩张", "产量", "销量", "capacity", "production"),
    "profit": ("净利润", "利润", "profit"),
    "risk": ("风险", "不确定", "risk"),
    "business": (
        "主要业务",
        "主营业务",
        "业务板块",
        "业务范围",
        "具体业务",
        "经营范围",
        "产品服务",
        "business",
    ),
}

REVENUE_STRUCTURE_FACT_TOKENS = ("收入结构", "分业务")
CAPACITY_FACT_TOKENS = ("产能", "产量", "销量", "扩张")
RISK_FACT_TOKENS = ("风险", "不确定", "波动", "冲突")
BUSINESS_METRIC_PREFIXES = ("business", "industry", "operation_scope")
BUSINESS_FACT_TOKENS = (
    "主营",
    "主要业务",
    "业务板块",
    "业务范围",
    "经营范围",
    "所属行业",
    "行业为",
    "产品",
    "服务",
    "软件开发",
    "系统集成",
    "技术开发",
    "技术服务",
)
CAPACITY_METRIC_PREFIXES = ("production_capacity", "production_volume", "sales_volume")
CHINESE_YEAR_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}
NUMERIC_UNIT_FACTORS = (
    ("万亿", 1_000_000_000_000),
    ("亿元", 100_000_000),
    ("亿", 100_000_000),
    ("万元", 10_000),
    ("千元", 1_000),
)


@dataclass(frozen=True, slots=True)
class FactRelevanceResult:
    core_facts: list[ExtractedFactRead] = field(default_factory=list)
    supporting_facts: list[ExtractedFactRead] = field(default_factory=list)
    intent_labels: list[str] = field(default_factory=list)


class FactRelevanceService:
    """Select facts that directly answer the research question.

    当前是可测试的规则层：先用问题意图约束事实展示顺序，避免报告首页被无关财务事实淹没。
    后续可替换为 embedding/LLM reranker，但输出契约应保持稳定。
    """

    def classify(
        self,
        *,
        question: str,
        facts: list[ExtractedFactRead],
    ) -> FactRelevanceResult:
        intents = self._detect_intents(question)
        if not facts:
            return FactRelevanceResult(intent_labels=sorted(intents))
        if not intents:
            return FactRelevanceResult(core_facts=facts, intent_labels=["general"])

        core: list[ExtractedFactRead] = []
        supporting: list[ExtractedFactRead] = []
        for fact in facts:
            score = self._score_fact(fact, intents)
            if score >= 2:
                core.append(fact)
            else:
                supporting.append(fact)
        core = self._rank_core_facts(core, intents, question)

        return FactRelevanceResult(
            core_facts=core,
            supporting_facts=supporting,
            intent_labels=sorted(intents),
        )

    def _detect_intents(self, question: str) -> set[str]:
        q = question.lower()
        intents = {
            intent
            for intent, tokens in INTENT_KEYWORDS.items()
            if any(token in q for token in tokens)
        }
        if "revenue_structure" in intents:
            intents.discard("revenue")
        return intents

    def _score_fact(self, fact: ExtractedFactRead, intents: set[str]) -> int:
        metric = (fact.metric_name or "").lower()
        claim = fact.claim.lower()
        score = 0

        if "rd" in intents and (metric.startswith("r&d") or "研发" in claim):
            score += 3
        if "revenue_structure" in intents and (
            metric.startswith("revenue_segment")
            or any(token in claim for token in REVENUE_STRUCTURE_FACT_TOKENS)
        ):
            score += 3
        if "revenue" in intents and (metric == "revenue" or "营业收入" in claim):
            score += 2
        if "capacity" in intents and (
            metric.startswith("production_capacity")
            or metric.startswith("production_volume")
            or metric.startswith("sales_volume")
            or any(token in claim for token in CAPACITY_FACT_TOKENS)
        ):
            score += 3
        if "profit" in intents and ("profit" in metric or "利润" in claim):
            score += 2
        if "risk" in intents and any(token in claim for token in RISK_FACT_TOKENS):
            score += 2
        if "business" in intents and (
            metric.startswith(BUSINESS_METRIC_PREFIXES)
            or any(token in claim for token in BUSINESS_FACT_TOKENS)
        ):
            score += 3

        return score

    def _rank_core_facts(
        self,
        facts: list[ExtractedFactRead],
        intents: set[str],
        question: str,
    ) -> list[ExtractedFactRead]:
        best_by_key: dict[tuple[str, str], ExtractedFactRead] = {}
        for fact in facts:
            key = (self._metric_family(fact), fact.period or "unknown_period")
            current = best_by_key.get(key)
            if current is None or self._fact_quality_score(fact) > self._fact_quality_score(current):
                best_by_key[key] = fact
        ranked_candidates = self._drop_unknown_period_when_known_period_exists(
            list(best_by_key.values())
        )
        ranked = sorted(
            ranked_candidates,
            key=lambda fact: (
                -self._period_rank(fact.period),
                self._metric_rank(fact, intents),
                -self._fact_quality_score(fact),
            ),
        )
        return self._filter_completed_multi_year_window(ranked, question)

    def _filter_completed_multi_year_window(
        self,
        facts: list[ExtractedFactRead],
        question: str,
    ) -> list[ExtractedFactRead]:
        window_years = self._requested_year_window(question)
        if window_years is None:
            return facts

        current_year = datetime.now(timezone.utc).year
        completed_facts = [
            fact for fact in facts if 0 < self._period_rank(fact.period) < current_year
        ]
        if not completed_facts:
            return facts

        latest_years = sorted(
            {self._period_rank(fact.period) for fact in completed_facts},
            reverse=True,
        )[:window_years]
        if len(latest_years) < min(window_years, 2):
            return facts
        allowed_years = set(latest_years)
        return [
            fact for fact in completed_facts if self._period_rank(fact.period) in allowed_years
        ]

    def _requested_year_window(self, question: str) -> int | None:
        normalized = question.replace(" ", "")
        digit_match = re.search(r"(?:近|最近)(\d{1,2})年", normalized)
        if digit_match:
            return max(1, min(int(digit_match.group(1)), 10))
        chinese_match = re.search(r"(?:近|最近)([一二两三四五六七八九十])年", normalized)
        if chinese_match:
            return CHINESE_YEAR_NUMBERS[chinese_match.group(1)]
        return None

    def _drop_unknown_period_when_known_period_exists(
        self, facts: list[ExtractedFactRead]
    ) -> list[ExtractedFactRead]:
        known_families = {
            self._metric_family(fact) for fact in facts if self._period_rank(fact.period)
        }
        return [
            fact
            for fact in facts
            if self._period_rank(fact.period) or self._metric_family(fact) not in known_families
        ]

    def _metric_family(self, fact: ExtractedFactRead) -> str:
        metric = (fact.metric_name or "").lower()
        if metric == "revenue":
            return "revenue"
        if "profit" in metric:
            return "profit"
        if metric.startswith("r&d"):
            return "rd"
        if metric.startswith("revenue_segment"):
            return "revenue_segment"
        if metric.startswith(CAPACITY_METRIC_PREFIXES):
            return metric.split(":", 1)[0]
        if metric.startswith(BUSINESS_METRIC_PREFIXES):
            return metric.split(":", 1)[0]
        return metric or "unknown"

    def _metric_rank(self, fact: ExtractedFactRead, intents: set[str]) -> int:
        family = self._metric_family(fact)
        if "revenue" in intents and family == "revenue":
            return 0
        if "profit" in intents and family == "profit":
            return 1
        if "rd" in intents and family == "rd":
            return 2
        if "revenue_structure" in intents and family == "revenue_segment":
            return 3
        if "capacity" in intents and family in {
            "production_capacity",
            "production_volume",
            "sales_volume",
        }:
            return 4
        if "business" in intents and family in {"business", "industry", "operation_scope"}:
            return 5
        return 9

    def _period_rank(self, period: str | None) -> int:
        if not period:
            return 0
        match = re.search(r"20\d{2}", period)
        return int(match.group(0)) if match else 0

    def _fact_quality_score(self, fact: ExtractedFactRead) -> float:
        period_score = 1_000_000_000 if self._period_rank(fact.period) else 0
        value_score = self._normalized_numeric_value(fact.value)
        return period_score + value_score + float(fact.confidence or 0)

    def _normalized_numeric_value(self, value: str | None) -> float:
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
