"""LLM Provider 抽象接口（仅局部能力，不控制工作流）。

注意：``check_compliance`` 默认实现走本地 deterministic 规则，所有 provider 共享一份判定结果，
绝对不允许把违规判定外包给远端模型，否则真实链路就失去可重放的合规审计基线。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from pydantic import Field

from app.compliance import ComplianceAction, evaluate_compliance_text
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.common import ComplianceStatus, SchemaBase
from app.schemas.fact import ExtractedFactCreate, ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from app.services.answer_pipeline import AnswerContext

# 违规改写时的提示与拒绝模板（DeepSeek / Qianfan / Mock 共用，保持口径一致）。
_COMPLIANCE_REWRITE_NOTICE = (
    "\n\n合规提示：本系统不提供证券投资导向结论。"
    "可继续提供基于公开资料的经营情况与风险信息分析。"
)
_COMPLIANCE_BLOCKED_TEMPLATE = (
    "当前请求涉及投资建议或个性化投融导向信息，已按合规策略拒绝。"
    "你可以继续询问：经营风险、财务变化、信息披露一致性、供应链稳定性等公开信息问题。"
)


class ComplianceCheckResult(SchemaBase):
    is_compliant: bool
    status: ComplianceStatus
    violations: list[str] = Field(default_factory=list)
    rewritten_text: str | None = None
    checked_at: datetime


def evaluate_compliance_for_provider(text: str) -> ComplianceCheckResult:
    """对 ``text`` 做规则层合规判定，统一返回 ``ComplianceCheckResult``。

    DeepSeek、Qianfan、Mock 三个 provider 都直接调用这个函数，不再各自维护一份。
    """
    decision = evaluate_compliance_text(text)
    violations = [hit.matched_snippet for hit in decision.hits]
    now = datetime.now(timezone.utc)

    if decision.action == ComplianceAction.ALLOW:
        return ComplianceCheckResult(
            is_compliant=True,
            status=ComplianceStatus.PASSED,
            violations=[],
            checked_at=now,
        )

    if decision.action == ComplianceAction.REWRITE:
        rewritten = text
        for phrase in violations:
            rewritten = rewritten.replace(phrase, "【已移除违规表达】")
        rewritten += _COMPLIANCE_REWRITE_NOTICE
        status = ComplianceStatus.REWRITTEN
    else:
        rewritten = _COMPLIANCE_BLOCKED_TEMPLATE
        status = ComplianceStatus.BLOCKED

    return ComplianceCheckResult(
        is_compliant=False,
        status=status,
        violations=violations,
        rewritten_text=rewritten,
        checked_at=now,
    )


class LLMProvider(ABC):
    """仅提供局部智能能力，不得决定 workflow 流程。"""

    @abstractmethod
    def extract_facts(
        self,
        task_id: str,
        company_name: str,
        question: str,
        chunks: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        raise NotImplementedError

    @abstractmethod
    def analyze_risks(
        self,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_report(
        self,
        task: ResearchTaskRead,
        verified_facts: list[ExtractedFactRead],
        conflicted_facts: list[ExtractedFactRead],
        insufficient_facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
        risk_analysis: str,
        citations: list[Citation],
        outdated_facts: list[ExtractedFactRead] | None = None,
        rejected_facts: list[ExtractedFactRead] | None = None,
        core_facts: list[ExtractedFactRead] | None = None,
        supporting_facts: list[ExtractedFactRead] | None = None,
        relevance_intents: list[str] | None = None,
        reader_summary: str | None = None,
        answer_context: AnswerContext | None = None,
    ) -> ReportCreate:
        raise NotImplementedError

    def check_compliance(self, text: str) -> ComplianceCheckResult:
        """默认走本地规则；provider 不应覆盖此方法，除非有更强的安全保证。"""
        return evaluate_compliance_for_provider(text)

    def rewrite_retrieval_query(self, question: str) -> str:
        """可选：将用户问题改写为更适合检索的表述。默认原样返回。"""
        return question.strip()

    def infer_research_time_scope(self, question: str) -> dict[str, object] | None:
        """可选：从问题推断时间倾向（window_years / explicit_years / strict）。默认不推断。"""
        return None
