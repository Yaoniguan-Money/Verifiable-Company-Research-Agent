"""Rule-based compliance checks.

本模块只提供可复用的规则结构与判定函数，不直接接入 workflow/API。
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.schemas.common import SchemaBase


class ComplianceViolationCategory(str, Enum):
    """违规类别（最小集合，支持后续扩展）。"""

    BUY_SELL_ADVICE = "buy_sell_advice"
    TARGET_PRICE = "target_price"
    RETURN_PROMISE = "return_promise"
    STOCK_RECOMMENDATION = "stock_recommendation"
    POSITION_GUIDANCE = "position_guidance"
    PERSONALIZED_INVESTMENT_ADVICE = "personalized_investment_advice"


class ComplianceAction(str, Enum):
    """处理动作。"""

    ALLOW = "allow"
    REWRITE = "rewrite"
    REFUSE = "refuse"


class ComplianceHit(SchemaBase):
    """单条命中结果。"""

    category: ComplianceViolationCategory
    matched_snippet: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class ComplianceDecision(SchemaBase):
    """合规模型最小输出结构。"""

    is_hit: bool
    action: ComplianceAction
    hits: list[ComplianceHit] = Field(default_factory=list)
    summary_reason: str = Field(..., min_length=1)


_CATEGORY_KEYWORDS: dict[ComplianceViolationCategory, list[str]] = {
    ComplianceViolationCategory.BUY_SELL_ADVICE: [
        "买入",
        "卖出",
        "要不要买",
        "能不能买",
        "能买吗",
        "should i buy",
        "buy",
        "sell",
    ],
    ComplianceViolationCategory.TARGET_PRICE: ["目标价", "target price", "target_price"],
    ComplianceViolationCategory.RETURN_PROMISE: ["收益承诺", "稳赚", "expected return", "收益预测"],
    ComplianceViolationCategory.STOCK_RECOMMENDATION: ["个股推荐", "推荐哪只", "推荐股票"],
    ComplianceViolationCategory.POSITION_GUIDANCE: ["加仓", "减仓", "持仓指导", "仓位"],
    ComplianceViolationCategory.PERSONALIZED_INVESTMENT_ADVICE: [
        "适合我买吗",
        "个性化投资建议",
        "适合你购买",
        "我该不该买",
    ],
}

_ALLOW_ANALYSIS_KEYWORDS = [
    "经营风险",
    "财务分析",
    "研发投入",
    "信息披露",
    "供应链风险",
    "公开资料",
]

_REFUSE_CATEGORIES = {
    ComplianceViolationCategory.BUY_SELL_ADVICE,
    ComplianceViolationCategory.STOCK_RECOMMENDATION,
    ComplianceViolationCategory.POSITION_GUIDANCE,
    ComplianceViolationCategory.PERSONALIZED_INVESTMENT_ADVICE,
}

_REWRITE_CATEGORIES = {
    ComplianceViolationCategory.TARGET_PRICE,
    ComplianceViolationCategory.RETURN_PROMISE,
}


def evaluate_compliance_text(text: str) -> ComplianceDecision:
    """最小合规判定。

    - 强违规类别（买卖建议/个股推荐/个性化建议等）：`refuse`
    - 可改写类别（目标价/收益承诺等）：`rewrite`
    - 未命中违规：`allow`
    """
    raw = (text or "").strip()
    if not raw:
        return ComplianceDecision(
            is_hit=False,
            action=ComplianceAction.ALLOW,
            hits=[],
            summary_reason="输入为空，按允许处理",
        )

    lowered = raw.lower()
    hits: list[ComplianceHit] = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in lowered:
                hits.append(
                    ComplianceHit(
                        category=category,
                        matched_snippet=kw,
                        reason=f"命中违规关键词：{kw}",
                    )
                )
                break

    if hits:
        categories = {h.category for h in hits}
        if categories & _REFUSE_CATEGORIES:
            action = ComplianceAction.REFUSE
            summary = "命中投资建议或个性化导向表达，需拒绝并转风险分析视角"
        elif categories & _REWRITE_CATEGORIES:
            action = ComplianceAction.REWRITE
            summary = "命中收益或价格预测表达，需改写为风险与公开信息分析表达"
        else:
            action = ComplianceAction.REFUSE
            summary = "命中违规表达，默认拒绝并转风险分析视角"
        return ComplianceDecision(
            is_hit=True,
            action=action,
            hits=hits,
            summary_reason=summary,
        )

    if any(k in raw for k in _ALLOW_ANALYSIS_KEYWORDS):
        return ComplianceDecision(
            is_hit=False,
            action=ComplianceAction.ALLOW,
            hits=[],
            summary_reason="属于经营/财务/风险分析范围，允许输出",
        )

    return ComplianceDecision(
        is_hit=False,
        action=ComplianceAction.ALLOW,
        hits=[],
        summary_reason="未命中违规规则，按允许处理",
    )

