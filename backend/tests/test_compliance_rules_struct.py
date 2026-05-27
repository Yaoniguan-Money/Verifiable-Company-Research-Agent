"""阶段 4.B：合规规则结构最小测试骨架。"""

from __future__ import annotations

from app.compliance import ComplianceAction, ComplianceViolationCategory, evaluate_compliance_text


def test_violation_should_refuse_with_structured_hits() -> None:
    decision = evaluate_compliance_text("这家公司现在能买吗？给我目标价。")
    assert decision.is_hit
    assert decision.action == ComplianceAction.REFUSE
    assert decision.hits
    assert any(h.category == ComplianceViolationCategory.TARGET_PRICE for h in decision.hits)


def test_return_promise_should_choose_rewrite() -> None:
    decision = evaluate_compliance_text("你预测一下收益，给我 expected return。")
    assert decision.is_hit
    assert decision.action == ComplianceAction.REWRITE
    assert any(h.category == ComplianceViolationCategory.RETURN_PROMISE for h in decision.hits)


def test_variant_phrase_should_be_caught() -> None:
    decision = evaluate_compliance_text("这家公司我现在要不要买？")
    assert decision.is_hit
    assert decision.action == ComplianceAction.REFUSE
    assert any(h.category == ComplianceViolationCategory.BUY_SELL_ADVICE for h in decision.hits)


def test_risk_analysis_should_allow() -> None:
    decision = evaluate_compliance_text("请分析该公司的经营风险和供应链不确定性。")
    assert not decision.is_hit
    assert decision.action == ComplianceAction.ALLOW


def test_empty_text_should_allow() -> None:
    decision = evaluate_compliance_text("   ")
    assert not decision.is_hit
    assert decision.action == ComplianceAction.ALLOW


def test_data_uri_base64_substring_should_not_false_positive() -> None:
    """内嵌图表 base64 可能含 buy 子串，不应误拦整份报告。"""
    blob = "ruFd52BuyxsotXYrVqww4Vl7hHXWjAYNGphVBN3Dsz"
    decision = evaluate_compliance_text(
        f"## 趋势\n\n![chart](data:image/png;base64,{blob})\n\n请分析经营风险。"
    )
    assert not decision.is_hit

