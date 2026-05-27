"""规则层合规判定（关键词命中 → 拒绝 / 改写 / 放行）。

本模块只暴露 ``evaluate_compliance_text``，下游（输入护栏、输出 reviewer、报告兜底）
共用同一份规则，不重复定义关键词。

判定优先级：
1. 命中 ``_REFUSE_CATEGORIES`` 中任一类别 → ``REFUSE``
2. 仅命中 ``_REWRITE_CATEGORIES`` → ``REWRITE``
3. 其它命中 → ``REFUSE``（默认拒绝，保守口径）
4. 未命中 → ``ALLOW``
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import Field

from app.schemas.common import SchemaBase


class ComplianceViolationCategory(str, Enum):
    """违规类别。"""

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
    """合规判定输出。"""

    is_hit: bool
    action: ComplianceAction
    hits: list[ComplianceHit] = Field(default_factory=list)
    summary_reason: str = Field(..., min_length=1)


# 关键词词典（中文 + ASCII 关键词混杂）。ASCII 关键词命中时按整词匹配，
# 避免 ``buy`` 这样的子串误命中 base64 图片或正常英文上下文。
_CATEGORY_KEYWORDS: dict[ComplianceViolationCategory, tuple[str, ...]] = {
    ComplianceViolationCategory.BUY_SELL_ADVICE: (
        "买入", "卖出", "要不要买", "能不能买", "能买吗", "建议买入", "建议卖出",
        "值得买", "值得卖", "抄底", "逃顶", "梭哈", "满仓", "清仓",
        "should i buy", "buy now", "sell now", "buy", "sell",
    ),
    ComplianceViolationCategory.TARGET_PRICE: (
        "目标价", "目标股价", "合理价位", "估值区间",
        "target price", "target_price", "price target",
    ),
    ComplianceViolationCategory.RETURN_PROMISE: (
        "收益承诺", "稳赚", "稳赚不赔", "保本保息", "翻倍", "十倍股",
        "年化收益", "预期收益", "expected return", "收益预测", "保证收益",
    ),
    ComplianceViolationCategory.STOCK_RECOMMENDATION: (
        "个股推荐", "推荐哪只", "推荐股票", "强烈推荐", "首选标的", "核心标的",
        "必买", "龙头首选",
    ),
    ComplianceViolationCategory.POSITION_GUIDANCE: (
        "加仓", "减仓", "持仓指导", "仓位", "建仓", "止盈", "止损",
        "调仓", "重仓", "轻仓",
    ),
    ComplianceViolationCategory.PERSONALIZED_INVESTMENT_ADVICE: (
        "适合我买吗", "个性化投资建议", "适合你购买", "我该不该买",
        "帮我选股票", "这只股票能买吗", "现在可以入场吗", "给我配置方案",
    ),
}

# 命中下列关键词时，即使无违规也提示"属于经营分析范围"，便于审计可读性。
_ALLOW_ANALYSIS_KEYWORDS: tuple[str, ...] = (
    "经营风险", "财务分析", "研发投入", "信息披露", "供应链风险", "公开资料",
)

_REFUSE_CATEGORIES = frozenset(
    {
        ComplianceViolationCategory.BUY_SELL_ADVICE,
        ComplianceViolationCategory.STOCK_RECOMMENDATION,
        ComplianceViolationCategory.POSITION_GUIDANCE,
        ComplianceViolationCategory.PERSONALIZED_INVESTMENT_ADVICE,
    }
)
_REWRITE_CATEGORIES = frozenset(
    {
        ComplianceViolationCategory.TARGET_PRICE,
        ComplianceViolationCategory.RETURN_PROMISE,
    }
)

# 报告中可能内嵌 base64 图表（Markdown ![alt](data:image/png;base64,...) ），
# 其随机字符串会偶发命中 "buy" / "sell"，扫描前先剥离。
_DATA_URI_PATTERN = re.compile(r"!\[[^\]]*\]\(data:[^)]+\)", re.IGNORECASE)


def _sanitize_compliance_text(text: str) -> str:
    """去掉 base64 图表等 data URI，避免随机子串误触关键词。"""
    return _DATA_URI_PATTERN.sub("", text)


def _ascii_keyword_hit(lowered: str, keyword: str) -> bool:
    """ASCII 关键词按整词命中；中文（非 ASCII）走 substring。"""
    if keyword.isascii() and keyword.isalpha() and " " not in keyword:
        return bool(re.search(rf"\b{re.escape(keyword.lower())}\b", lowered))
    return keyword.lower() in lowered


def _allow_decision(reason: str) -> ComplianceDecision:
    return ComplianceDecision(
        is_hit=False,
        action=ComplianceAction.ALLOW,
        hits=[],
        summary_reason=reason,
    )


def evaluate_compliance_text(text: str) -> ComplianceDecision:
    """对外唯一入口。

    Args:
        text: 用户输入或模型输出。允许 None / 空字符串。

    Returns:
        ``ComplianceDecision``：``is_hit`` 表示是否命中违规；``action`` 决定下游动作。
    """
    raw = _sanitize_compliance_text((text or "").strip())
    if not raw:
        return _allow_decision("输入为空，按允许处理")

    lowered = raw.lower()
    hits: list[ComplianceHit] = []
    # 每个类别最多记录一个 hit（取首次命中的关键词），减少重复审计噪音。
    for category, keywords in _CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if _ascii_keyword_hit(lowered, kw):
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

    if any(keyword in raw for keyword in _ALLOW_ANALYSIS_KEYWORDS):
        return _allow_decision("属于经营/财务/风险分析范围，允许输出")
    return _allow_decision("未命中违规规则，按允许处理")
