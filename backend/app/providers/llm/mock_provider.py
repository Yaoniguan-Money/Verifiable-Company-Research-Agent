"""MockLLMProvider：阶段 1 的局部能力占位实现。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.compliance import ComplianceAction, evaluate_compliance_text
from app.providers.llm.base import ComplianceCheckResult, LLMProvider
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.common import ComplianceStatus
from app.schemas.fact import ExtractedFactCreate, ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from app.services.report_renderer import MockReportRenderer, ReportRenderInput


class MockLLMProvider(LLMProvider):
    """基于规则返回结构化 mock 结果。"""

    def extract_facts(
        self,
        task_id: str,
        company_name: str,
        question: str,
        chunks: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        facts: list[ExtractedFactCreate] = []
        for idx, chunk in enumerate(chunks):
            claim = f"{company_name} 公开资料片段#{idx + 1}提到研发与经营风险信息"
            facts.append(
                ExtractedFactCreate(
                    task_id=task_id,
                    claim=claim,
                    metric_name="R&D_and_operation_signal",
                    value="公开资料可见持续投入与风险提示",
                    period="近三年",
                    source_id=chunk.source_id,
                    chunk_id=chunk.id,
                    confidence=0.75,
                )
            )
        return facts

    def analyze_risks(
        self,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
    ) -> str:
        verified_count = sum(1 for item in verification_results if item.status == "verified")
        insufficient_count = sum(
            1 for item in verification_results if item.status == "insufficient"
        )
        conflicted_count = sum(1 for item in verification_results if item.status == "conflicted")

        return (
            f"围绕“{company_name}”与问题“{question}”的公开信息分析显示："
            f"已验证事实 {verified_count} 条，证据不足 {insufficient_count} 条，"
            f"存在冲突 {conflicted_count} 条。建议持续关注原材料成本波动、"
            "供应链稳定性、海外扩张执行节奏与信息披露一致性。"
        )

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
    ) -> ReportCreate:
        return MockReportRenderer().render(
            ReportRenderInput(
                task=task,
                core_facts=core_facts or [],
                supporting_facts=supporting_facts or [],
                relevance_intents=relevance_intents or [],
                verified_facts=verified_facts,
                conflicted_facts=conflicted_facts,
                insufficient_facts=insufficient_facts,
                verification_results=verification_results,
                risk_analysis=risk_analysis,
                citations=citations,
                outdated_facts=outdated_facts or [],
                rejected_facts=rejected_facts or [],
            )
        )

    def check_compliance(self, text: str) -> ComplianceCheckResult:
        decision = evaluate_compliance_text(text)
        violations = [h.matched_snippet for h in decision.hits]
        if decision.action == ComplianceAction.ALLOW:
            return ComplianceCheckResult(
                is_compliant=True,
                status=ComplianceStatus.PASSED,
                violations=[],
                checked_at=datetime.now(timezone.utc),
            )

        if decision.action == ComplianceAction.REWRITE:
            rewritten = text
            for phrase in violations:
                rewritten = rewritten.replace(phrase, "【已移除违规表达】")
            rewritten += (
                "\n\n合规提示：本系统不提供证券投资导向结论。"
                "可继续提供基于公开资料的经营情况与风险信息分析。"
            )
            status = ComplianceStatus.REWRITTEN
        else:
            rewritten = (
                "当前请求涉及投资建议或个性化投融导向信息，已按合规策略拒绝。"
                "你可以继续询问：经营风险、财务变化、信息披露一致性、供应链稳定性等公开信息问题。"
            )
            status = ComplianceStatus.BLOCKED

        return ComplianceCheckResult(
            is_compliant=False,
            status=status,
            violations=violations,
            rewritten_text=rewritten,
            checked_at=datetime.now(timezone.utc),
        )
