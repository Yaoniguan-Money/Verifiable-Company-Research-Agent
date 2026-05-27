"""MockLLMProvider：本地 deterministic 实现，dev/test 默认走这条路。"""

from __future__ import annotations

from app.providers.llm.base import LLMProvider
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.fact import ExtractedFactCreate, ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from app.services.answer_pipeline import AnswerContext
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
        reader_summary: str | None = None,
        answer_context: AnswerContext | None = None,
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
                reader_summary=reader_summary,
                answer_context=answer_context,
            )
        )

    def rewrite_retrieval_query(self, question: str) -> str:
        return f"{question.strip()} 公开披露 财务指标 经营风险"

    # check_compliance 走 LLMProvider 基类默认实现（本地规则裁定）。
