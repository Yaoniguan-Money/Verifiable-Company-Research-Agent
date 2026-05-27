from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True, slots=True)
class MetricFamily:
    id: str
    base_metrics: tuple[str, ...]
    intent_tokens: tuple[str, ...]
    claim_tokens: tuple[str, ...]
    preferred_metric_for_family: str
    unit_families: tuple[str, ...]


_DEFAULT_FAMILIES: tuple[MetricFamily, ...] = (
    MetricFamily(
        id="rd",
        base_metrics=("r&d", "rd", "r_and_d", "research_development", "R&D_expenditure", "R&D_total_spending"),
        intent_tokens=("研发", "r&d", "rd", "research", "研发费用", "研发投入"),
        claim_tokens=("研发", "研究开发", "研发费用", "研发投入"),
        preferred_metric_for_family="R&D_total_spending",
        unit_families=("money",),
    ),
    MetricFamily(
        id="profit",
        base_metrics=("profit", "net_profit", "net_profit_parent", "net_profit_deducted"),
        intent_tokens=("利润", "净利润", "归母", "profit"),
        claim_tokens=("利润", "净利润", "归母", "扣非"),
        preferred_metric_for_family="net_profit_parent",
        unit_families=("money",),
    ),
    MetricFamily(
        id="revenue",
        base_metrics=("revenue", "operating_revenue", "sales_revenue"),
        intent_tokens=("收入", "营收", "营业收入", "revenue"),
        claim_tokens=("收入", "营收", "营业收入"),
        preferred_metric_for_family="revenue",
        unit_families=("money",),
    ),
    MetricFamily(
        id="revenue_structure",
        base_metrics=("revenue_segment", "segment_revenue"),
        intent_tokens=("收入结构", "营收结构", "分业务", "业务结构", "收入构成"),
        claim_tokens=("收入结构", "分业务", "分产品", "构成"),
        preferred_metric_for_family="revenue_segment",
        unit_families=("money", "ratio"),
    ),
    MetricFamily(
        id="capacity",
        base_metrics=("production_capacity", "production_volume", "sales_volume", "capacity"),
        intent_tokens=("产能", "扩张", "产量", "销量", "capacity", "production"),
        claim_tokens=("产能", "产量", "销量", "交付量"),
        preferred_metric_for_family="production_capacity",
        unit_families=("volume", "count"),
    ),
    MetricFamily(
        id="business",
        base_metrics=("business", "industry", "operation_scope"),
        intent_tokens=(
            "主要业务",
            "主营业务",
            "业务板块",
            "业务范围",
            "具体业务",
            "经营范围",
            "产品服务",
            "business",
        ),
        claim_tokens=("主营", "业务", "经营范围", "产品", "服务"),
        preferred_metric_for_family="business",
        unit_families=("text",),
    ),
    MetricFamily(
        id="risk",
        base_metrics=("risk", "uncertainty"),
        intent_tokens=("风险", "不确定", "risk"),
        claim_tokens=("风险", "不确定", "波动"),
        preferred_metric_for_family="risk",
        unit_families=("text",),
    ),
)


class MetricRegistry:
    """Single source for metric-family matching used by intent and answer code."""

    def __init__(self, families: tuple[MetricFamily, ...] = _DEFAULT_FAMILIES) -> None:
        self._families = {family.id: family for family in families}

    @property
    def families(self) -> dict[str, MetricFamily]:
        return dict(self._families)

    def get(self, family_id: str) -> MetricFamily | None:
        return self._families.get(family_id)

    def detect_families(self, text: str) -> frozenset[str]:
        value = (text or "").lower()
        matches = {
            family.id
            for family in self._families.values()
            if any(token.lower() in value for token in family.intent_tokens)
        }
        if "revenue_structure" in matches:
            matches.discard("revenue")
        return frozenset(matches)

    def matches_family(
        self,
        *,
        metric_name: str | None,
        claim: str,
        family_ids: frozenset[str] | set[str],
    ) -> bool:
        if not family_ids:
            return True
        metric = (metric_name or "").lower()
        claim_l = (claim or "").lower()
        for family_id in family_ids:
            family = self._families.get(family_id)
            if family is None:
                continue
            tokens = family.base_metrics + family.claim_tokens
            if any(token.lower() in metric or token.lower() in claim_l for token in tokens):
                return True
        return False

    def preferred_metric(self, family_id: str) -> str | None:
        family = self._families.get(family_id)
        return family.preferred_metric_for_family if family else None


@lru_cache
def get_metric_registry() -> MetricRegistry:
    return MetricRegistry()

