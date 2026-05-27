from __future__ import annotations

from app.schemas.common import ComplianceStatus
from app.services.chat_guardrail import ChatGuardrailService


def test_chat_guardrail_blocks_buy_advice() -> None:
    service = ChatGuardrailService()
    result = service.guard_assistant_output("我建议你现在买入并加仓。")
    assert not result.is_compliant
    assert result.status == ComplianceStatus.BLOCKED
    assert result.rewritten_text is not None
    assert "已按合规策略拒绝" in result.rewritten_text


def test_chat_guardrail_allows_risk_analysis() -> None:
    service = ChatGuardrailService()
    result = service.guard_assistant_output("可以继续分析该公司的供应链风险与财务变化。")
    assert result.is_compliant
    assert result.status == ComplianceStatus.PASSED
