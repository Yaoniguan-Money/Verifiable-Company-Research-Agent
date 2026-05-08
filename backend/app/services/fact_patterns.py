"""结构化事实抽取规则。

当前仍是规则抽取，目标是让主流程稳定、可测试；后续替换为 LLM/表格解析器时，
优先保持这里定义的指标名称和输出契约不变。
"""

from __future__ import annotations

from dataclasses import dataclass

NUMBER_PATTERN = r"\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"
VALUE_UNIT_PATTERN = rf"(?P<value>{NUMBER_PATTERN})\s*(?P<unit>亿元|亿|千元|万元|元|%|辆|台|万辆|万台|吨|万吨|GWh|MWh)"
ALT_VALUE_UNIT_PATTERN = rf"(?P<value_alt>{NUMBER_PATTERN})\s*(?P<unit_alt>亿元|亿|千元|万元|元|%|辆|台|万辆|万台|吨|万吨|GWh|MWh)"
INLINE_VALUE_UNIT_PATTERN = rf"(?P<value_inline>{NUMBER_PATTERN})\s*(?P<unit_inline>亿元|亿|千元|万元|元|%|辆|台|万辆|万台|吨|万吨|GWh|MWh)"
YEAR_PATTERN = r"(?P<year>20\d{2})\s*年"

METRIC_LABELS = {
    "R&D_expenditure": "研发投入",
    "revenue": "营业收入",
    "net_profit": "净利润",
    "net_profit_parent": "归母净利润",
    "net_profit_deducted": "扣非净利润",
    "revenue_segment": "分业务收入",
    "production_capacity": "产能",
    "production_volume": "产量",
    "sales_volume": "销量",
}


@dataclass(frozen=True, slots=True)
class FactRule:
    pattern: str
    metric_name: str


FACT_RULES: tuple[FactRule, ...] = (
    FactRule(
        pattern=r"(?:研发投入|研发费用)(?:为|达到|约为|实现|超|超过|高于|达|：|:)?\s*"
        + VALUE_UNIT_PATTERN,
        metric_name="R&D_expenditure",
    ),
    FactRule(
        pattern=(
            r"(?:"
            + VALUE_UNIT_PATTERN
            + r"\s*(?:用于|投向)?(?:研发投入|研发费用|研发)|研发(?:投入|费用)?(?:超|超过|高于|达)\s*"
            + ALT_VALUE_UNIT_PATTERN
            + r")"
        ),
        metric_name="R&D_expenditure",
    ),
    FactRule(
        pattern=r"(?:营收|营业收入|营业总收入)(?:为|达到|约为|实现|：|:)?\s*"
        + VALUE_UNIT_PATTERN,
        metric_name="revenue",
    ),
    FactRule(
        pattern=r"(?:归母净利润|归属于上市公司股东的净利润)(?:为|达到|约为|实现|：|:)?\s*"
        + VALUE_UNIT_PATTERN,
        metric_name="net_profit_parent",
    ),
    FactRule(
        pattern=r"(?:扣非净利润|扣非归母净利润|扣除非经常性损益后的净利润)(?:为|达到|约为|实现|：|:)?\s*"
        + VALUE_UNIT_PATTERN,
        metric_name="net_profit_deducted",
    ),
    FactRule(
        pattern=r"(?:净利润)(?:为|达到|约为|实现|：|:)?\s*" + VALUE_UNIT_PATTERN,
        metric_name="net_profit",
    ),
    FactRule(
        pattern=r"(?P<segment>[\u4e00-\u9fa5A-Za-z0-9、及与/（）() -]{2,40})(?:收入|销售收入)(?:为|达到|约为|实现|：|:)?\s*"
        + VALUE_UNIT_PATTERN,
        metric_name="revenue_segment",
    ),
    FactRule(
        pattern=r"(?P<product>[\u4e00-\u9fa5A-Za-z0-9、及与/（）() -]{2,30})?(?:产能状况|产能)(?:为|达到|约为|：|:)?\s*"
        + VALUE_UNIT_PATTERN,
        metric_name="production_capacity",
    ),
    FactRule(
        pattern=r"(?P<product>[\u4e00-\u9fa5A-Za-z0-9、及与/（）() -]{2,30})?(?:产量|快报产量)(?:为|达到|约为|：|:)?\s*"
        + VALUE_UNIT_PATTERN,
        metric_name="production_volume",
    ),
    FactRule(
        pattern=r"(?P<product>[\u4e00-\u9fa5A-Za-z0-9、及与/（）() -]{2,30})?(?:销量|快报销量)(?:为|达到|约为|：|:)?\s*"
        + VALUE_UNIT_PATTERN,
        metric_name="sales_volume",
    ),
)
