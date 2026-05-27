"""输出层语义合规辅助（轻量分类，不替代规则层）。"""

from __future__ import annotations

from app.compliance.rules import evaluate_compliance_text

_INVESTMENT_TONE = (
    "强烈建议",
    "必买",
    "稳赚",
    "目标价",
    "买入时机",
    "卖出时机",
    "推荐配置",
)


def classify_investment_tone(text: str) -> str:
    """返回 passed / rewritable / blocked。"""
    base = evaluate_compliance_text(text)
    if base.action.value == "refuse":
        return "blocked"
    if base.action.value == "rewrite":
        return "rewritable"
    lowered = text.lower()
    if any(token in lowered for token in _INVESTMENT_TONE):
        return "rewritable"
    return "passed"
