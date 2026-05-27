from __future__ import annotations

from app.providers.factory import ProviderFactory
from app.providers.llm import LLMProvider
from app.providers.llm.base import ComplianceCheckResult


class ChatGuardrailService:
    """chat 场景最小预留：统一复用现有合规判定口径。"""

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider or ProviderFactory().create_llm_provider()

    def guard_user_message(self, text: str) -> ComplianceCheckResult:
        """检查用户追问是否越过投资建议边界。"""
        return self._guard_text(text)

    def guard_assistant_output(self, text: str) -> ComplianceCheckResult:
        """检查最终输出，保留旧入口以兼容既有测试和调用。"""
        return self._guard_text(text)

    def _guard_text(self, text: str) -> ComplianceCheckResult:
        check = self.llm_provider.check_compliance(text)
        if check.is_compliant:
            return check
        if check.rewritten_text:
            return check
        return check.model_copy(
            update={
                "rewritten_text": (
                    "当前问题涉及投资建议导向内容，已按合规策略拒绝。"
                    "请改为企业经营、财务变化、信息披露或风险分析问题。"
                )
            }
        )
