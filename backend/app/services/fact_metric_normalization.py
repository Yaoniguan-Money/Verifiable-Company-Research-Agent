"""Normalize metric names for deterministic fact verification."""

from __future__ import annotations

import re

_DIMENSIONAL_METRICS = {
    "revenue_segment",
    "production_capacity",
    "production_volume",
    "sales_volume",
}

_ALIASES = {
    "r&d_expenditure": "R&D_expenditure",
    "r_and_d": "R&D_expenditure",
    "rd": "R&D_expenditure",
    "rd_expense": "R&D_expenditure",
    "research_expense": "R&D_expenditure",
    "research_expenditure": "R&D_expenditure",
    "\u7814\u53d1\u8d39\u7528": "R&D_expenditure",
    "r&d_total_spending": "R&D_total_spending",
    "rd_total": "R&D_total_spending",
    "rd_spending": "R&D_total_spending",
    "\u7814\u53d1\u6295\u5165": "R&D_total_spending",
    "\u7814\u53d1\u6295\u5165\u5408\u8ba1": "R&D_total_spending",
    "rev": "revenue",
    "operating_revenue": "revenue",
    "\u8425\u4e1a\u6536\u5165": "revenue",
    "\u8425\u6536": "revenue",
    "np": "net_profit",
    "\u51c0\u5229\u6da6": "net_profit",
    "parent_net_profit": "net_profit_parent",
    "\u5f52\u6bcd\u51c0\u5229\u6da6": "net_profit_parent",
    "deducted_net_profit": "net_profit_deducted",
    "\u6263\u975e\u51c0\u5229\u6da6": "net_profit_deducted",
    "\u6263\u975e\u5f52\u6bcd\u51c0\u5229\u6da6": "net_profit_deducted",
}


class FactMetricNormalizer:
    """Build stable metric keys while preserving important accounting boundaries."""

    def comparable_key(self, metric_name: str | None) -> str:
        if not metric_name:
            return ""

        base, dimension = self._split_dimension(metric_name)
        normalized_base = self._normalize_base(base)
        if normalized_base in _DIMENSIONAL_METRICS and dimension:
            return f"{normalized_base}:{self._normalize_dimension(dimension)}"
        return normalized_base

    def _split_dimension(self, metric_name: str) -> tuple[str, str | None]:
        if ":" not in metric_name:
            return metric_name, None
        base, dimension = metric_name.split(":", 1)
        return base, dimension

    def _normalize_base(self, metric_name: str) -> str:
        key = metric_name.strip().lower()
        key = key.replace(" ", "_").replace("-", "_")
        key = re.sub(r"_+", "_", key)
        return _ALIASES.get(key, metric_name.strip())

    def _normalize_dimension(self, dimension: str) -> str:
        cleaned = dimension.strip().lower()
        cleaned = re.sub(r"[\s\u3000]+", "", cleaned)
        cleaned = cleaned.replace("\uff08", "(").replace("\uff09", ")")
        return cleaned
