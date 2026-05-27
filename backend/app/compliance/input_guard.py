"""输入层合规：用户问题扫描。"""

from __future__ import annotations

from app.compliance.rules import ComplianceAction, evaluate_compliance_text


def evaluate_user_input(text: str) -> tuple[bool, str | None]:
    """返回 (allowed, rejection_message)。投资建议类直接拒绝。"""
    decision = evaluate_compliance_text(text)
    if not decision.is_hit:
        return True, None
    if decision.action == ComplianceAction.REFUSE:
        return False, (
            "当前问题涉及投资建议或个性化投融导向，已按合规策略拒绝。"
            "系统仅支持基于公开资料的经营与风险分析。"
            "请改写为：财务变化、研发投入、信息披露、供应链与经营风险等中性问题。"
        )
    return True, None
