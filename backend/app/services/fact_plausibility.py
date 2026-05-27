"""抽取事实的合理性校验，过滤 PDF 误解析与口径明显异常的值。"""

from __future__ import annotations

import re
from decimal import Decimal

from app.services.fact_value_normalization import FactValueNormalizer

# 上市公司研发投入/营收以「元」计通常至少千万级；低于 1 亿元多为章节号或比例误匹配。
_MIN_LISTED_COMPANY_MONEY_YUAN = Decimal("100000000")

_CUMULATIVE_RD_PATTERN = re.compile(r"累计.{0,12}(?:研发|R&D)")
_SECTION_NUMBER_VALUE_PATTERN = re.compile(
    r"^\s*(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?P<sep>[、.．])"
)

_MONEY_METRICS = frozenset(
    {
        "R&D_expenditure",
        "R&D_total_spending",
        "revenue",
        "revenue_segment",
        "net_profit",
        "net_profit_parent",
        "net_profit_deducted",
    }
)

METRIC_UNIT_RULES: dict[str, frozenset[str]] = {
    "R&D_expenditure": frozenset({"money"}),
    "R&D_total_spending": frozenset({"money"}),
    "revenue": frozenset({"money"}),
    "revenue_segment": frozenset({"money"}),
    "net_profit": frozenset({"money"}),
    "net_profit_parent": frozenset({"money"}),
    "net_profit_deducted": frozenset({"money"}),
    "production_capacity": frozenset({"vehicle", "unit", "ton", "energy"}),
    "production_volume": frozenset({"vehicle", "unit", "ton", "energy"}),
    "sales_volume": frozenset({"vehicle", "unit", "ton", "energy"}),
}


def is_section_heading_line(line: str) -> bool:
    """章节标题如「4、研发投入」，不是带金额的表格行。"""
    cleaned = line.strip()
    if not _SECTION_NUMBER_VALUE_PATTERN.match(cleaned):
        return False
    # 行内若已有典型财报金额（千分位 + 小数），则按数据行处理。
    return not re.search(r"\d{1,3}(?:,\d{3})+\.\d{2}", cleaned)


def is_section_number_token(*, line: str, start: int, end: int) -> bool:
    """判断裸数字是否为「4、」这类章节序号，而非金额。"""
    if end < len(line) and line[end] in "、.．":
        return True
    return False


def is_implausible_extracted_value(
    metric_name: str,
    value: str,
    *,
    line: str | None = None,
    context: str | None = None,
) -> bool:
    """返回 True 表示应丢弃该抽取结果。"""
    base = (metric_name or "").split(":", 1)[0]
    value = (value or "").strip()
    probe = f"{line or ''}\n{context or ''}"

    if base == "R&D_expenditure" and _CUMULATIVE_RD_PATTERN.search(probe):
        return True

    # 百分比后面常带空格或换行，先 strip，避免金额指标误放行。
    if value.endswith("%"):
        if base in _MONEY_METRICS:
            return True
        return False

    normalized = FactValueNormalizer().normalize(value)
    allowed_kinds = METRIC_UNIT_RULES.get(base)
    if normalized is not None and allowed_kinds and normalized.kind not in allowed_kinds:
        return True
    if normalized is None or normalized.kind != "money":
        return False

    if base in _MONEY_METRICS and normalized.value < _MIN_LISTED_COMPANY_MONEY_YUAN:
        return True
    return False
