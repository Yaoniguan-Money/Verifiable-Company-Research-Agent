from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.init_db import ensure_lightweight_schema_updates
from app.db.models import EvidenceChunk, ExtractedFact, ResearchTask, VerificationResult
from app.db.models import TaskStatus as TaskStatusORM
from app.providers.factory import ProviderFactory
from app.providers.llm import LLMProvider
from app.providers.search import SearchProvider
from app.repositories import ResearchArtifactRepository, ResearchTaskRepository
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.common import (
    ComplianceStatus,
    source_quality_counts,
    source_quality_insufficient,
)
from app.schemas.fact import ExtractedFactCreate, ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.retrieval import RetrievedEvidence
from app.schemas.source import SourceRead
from app.schemas.verification import VerificationResultRead
from app.schemas.workflow import WorkflowDecision, WorkflowState
from app.services.fact_extraction import FactExtractionService
from app.services.fact_verification import FactVerificationService
from app.services.ingestion import IngestionService
from app.services.report_assembly import ReportAssemblyService
from app.services.report_charts import append_charts_section
from app.services.report_evidence import ReportEvidenceService
from app.services.workflow_audit import WorkflowAuditService
from app.services.workflow_events import get_workflow_event_bus

logger = logging.getLogger(__name__)

ComplianceAction = Literal["passed", "rewrite", "blocked"]
_MAX_CHART_FACTS = 6
_REPORT_BLOCKED_FALLBACK = (
    "当前请求涉及投资建议导向内容，已按合规策略拒绝输出。"
    "你可以继续查询企业经营、财务变化、信息披露与风险分析。"
)
_VERIFICATION_STATUS_LABELS: dict[str, str] = {
    "verified": "已验证",
    "conflicted": "冲突",
    "insufficient": "证据不足",
    "outdated": "过时",
    "rejected": "已排除",
}


@dataclass(frozen=True)
class SourceQualityResult:
    summary: dict[str, Any]
    insufficient: bool


@dataclass(frozen=True)
class EmbeddingIndexResult:
    embedding_results: list[dict[str, Any]]
    evidence_chunks: list[EvidenceChunkRead]


@dataclass(frozen=True)
class ReportBuildResult:
    report: ReportCreate
    citations: list[Citation]


@dataclass(frozen=True)
class ComplianceCheckOutcome:
    action: ComplianceAction
    decision: dict[str, Any]


def _to_chunk_read(chunk: EvidenceChunk) -> EvidenceChunkRead:
    return EvidenceChunkRead(
        id=chunk.id,
        source_id=chunk.source_id,
        task_id=chunk.task_id,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        metadata=chunk.chunk_metadata,
        embedding_id=chunk.embedding_id,
        created_at=chunk.created_at,
    )


def _verification_status_value(item: VerificationResult | VerificationResultRead) -> str:
    return str(getattr(item.status, "value", item.status))


def _format_verification_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "无校验结果"
    return "；".join(
        f"{_VERIFICATION_STATUS_LABELS.get(key, key)} {value} 条"
        for key, value in sorted(counts.items())
    )


def _chart_payload_from_facts(
    facts: list[ExtractedFactRead],
) -> tuple[list[str], list[float]]:
    labels: list[str] = []
    values: list[float] = []
    chart_facts = [
        fact
        for fact in facts
        if any(
            token in (fact.metric_name or "").lower()
            for token in ("revenue", "profit", "net_profit")
        )
    ] or facts
    for fact in chart_facts[:_MAX_CHART_FACTS]:
        if not fact.period or not fact.value:
            continue
        digits = "".join(ch for ch in str(fact.value) if ch.isdigit() or ch == ".")
        if not digits:
            continue
        try:
            values.append(float(digits))
        except ValueError:
            continue
        labels.append(str(fact.period))
    return labels, values


class ResearchDomainServices:
    """Shared business capabilities for LangGraph and service workflows."""

    def __init__(
        self,
        *,
        db: Session,
        settings: Settings,
        artifacts: ResearchArtifactRepository,
        search_provider: SearchProvider,
        llm_provider: LLMProvider,
        audit: WorkflowAuditService,
    ) -> None:
        self.db = db
        self.settings = settings
        self.artifacts = artifacts
        self.tasks = ResearchTaskRepository(db)
        self.search_provider = search_provider
        self.llm_provider = llm_provider
        self.audit = audit
        self.report_evidence = ReportEvidenceService(db)

    def load_task(self, task_id: str) -> ResearchTask:
        return self._task(task_id)

    def workflow_status(self, task_id: str) -> WorkflowState | None:
        task = self.tasks.get(task_id)
        if task is None:
            return None
        status_value = getattr(task.status, "value", str(task.status))
        return WorkflowState(
            task_id=task.id,
            company_name=task.company_name,
            question=task.question,
            status=status_value,
        )

    def collect_sources(self, task_id: str) -> list[SourceRead]:
        task = self._task(task_id)
        source_schemas = self.search_provider.search(task.company_name, task.question)
        self.artifacts.add_sources(task_id=task.id, sources=source_schemas)
        self.db.commit()
        return [SourceRead.model_validate(item) for item in self.artifacts.list_sources(task.id)]

    def evaluate_source_quality(self, task_id: str) -> SourceQualityResult:
        sources = self.artifacts.list_sources(task_id)
        authority_counts, layer_counts = source_quality_counts(sources)
        return SourceQualityResult(
            summary={
                "authority_counts": authority_counts,
                "layer_counts": layer_counts,
                "source_count": len(sources),
            },
            insufficient=source_quality_insufficient(sources),
        )

    def record_source_quality_gap(self, task_id: str) -> WorkflowDecision:
        return WorkflowDecision(
            node="record_source_quality_gap_node",
            reason="source_quality_insufficient",
            message=(
                "Source quality gate found insufficient high-authority or official-body "
                "evidence; report must keep source limitations visible."
            ),
            task_id=task_id,
        )

    def ingest_chunks(self, task_id: str) -> list[EvidenceChunkRead]:
        pipeline = ProviderFactory(self.settings).create_content_enrichment_pipeline() if self.settings.content_enrichment_enabled else None
        ingestion = IngestionService(self.db, enrichment_pipeline=pipeline)
        for source in self.artifacts.list_sources(task_id):
            ingestion.ingest_chunks_for_source(
                task_id,
                source.id,
                chunk_size=self.settings.workflow_chunk_size,
                chunk_overlap=self.settings.workflow_chunk_overlap,
            )
        self.db.commit()
        return [_to_chunk_read(item) for item in self.artifacts.list_chunks(task_id)]

    def embed_chunks(self, task_id: str) -> EmbeddingIndexResult:
        results = self.report_evidence.embed_and_index_chunks(task_id)
        self.db.commit()
        return EmbeddingIndexResult(
            embedding_results=[
                {
                    "chunk_id": item.chunk_id,
                    "embedding_id": item.embedding_id,
                    "dimension": item.dimension,
                }
                for item in results
            ],
            evidence_chunks=[_to_chunk_read(item) for item in self.artifacts.list_chunks(task_id)],
        )

    def retrieve_evidence(
        self,
        *,
        task_id: str,
        indexed_chunk_count: int,
    ) -> list[RetrievedEvidence]:
        return self.report_evidence.retrieve_evidence_for_task(
            task=self._task(task_id),
            indexed_chunk_count=indexed_chunk_count,
        )

    def extract_facts(self, task_id: str) -> list[ExtractedFactRead]:
        task = self._task(task_id)
        chunk_reads = [_to_chunk_read(row) for row in self.artifacts.list_chunks(task.id)]

        # Step 1: 正则快速抽取（表格 + 叙述句），作为 baseline
        extraction = FactExtractionService().extract_from_chunks(
            task_id=task.id,
            company_name=task.company_name,
            question=task.question,
            chunks=chunk_reads,
        )
        extracted_facts = extraction.facts

        # Step 2: 正则粗筛 → Embedding 排序 → LLM 依次送检，意图命中即停
        if self.settings.llm_provider != "mock" and chunk_reads:
            llm_facts = self._llm_ranked_extract(task, chunk_reads)
            if llm_facts:
                seen = {(f.source_id, f.metric_name, f.period, f.value) for f in extracted_facts}
                for f in llm_facts:
                    key = (f.source_id, f.metric_name, f.period, f.value)
                    if key not in seen:
                        extracted_facts.append(f)
                        seen.add(key)

        self.artifacts.add_facts(
            [
                ExtractedFact(
                    task_id=item.task_id,
                    claim=item.claim,
                    metric_name=item.metric_name,
                    value=item.value,
                    period=item.period,
                    source_id=item.source_id,
                    chunk_id=item.chunk_id,
                    confidence=item.confidence,
                )
                for item in extracted_facts
            ]
        )
        self.db.commit()
        return [
            ExtractedFactRead.model_validate(item) for item in self.artifacts.list_facts(task.id)
        ]

    def verify_facts(self, task_id: str) -> list[VerificationResultRead]:
        fact_rows = self.artifacts.list_facts(task_id)
        if not fact_rows:
            return []

        output = FactVerificationService().verify_facts(
            task_id=task_id,
            facts=[ExtractedFactRead.model_validate(item) for item in fact_rows],
            source_context=self.artifacts.source_context(task_id),
        )
        verifications = [
            VerificationResult(
                fact_id=item.fact_id,
                task_id=item.task_id,
                status=item.status.value,
                confidence=item.confidence,
                supporting_sources=item.supporting_sources,
                conflicting_sources=item.conflicting_sources,
                reason=item.reason,
                reason_code=item.reason_code,
            )
            for item in output.results
        ]
        ensure_lightweight_schema_updates(self.db.get_bind())
        self.artifacts.add_verifications(verifications)
        self.db.commit()
        return [
            VerificationResultRead.model_validate(item)
            for item in self.artifacts.list_verifications(task_id)
        ]

    def record_evidence_gap(self, task_id: str) -> WorkflowDecision:
        return WorkflowDecision(
            node="record_evidence_gap_node",
            reason="no_extracted_facts",
            message="没有抽取到结构化事实，已跳过事实校验；报告只能说明证据缺口。",
            task_id=task_id,
        )

    def record_verification_risk(self, task_id: str) -> WorkflowDecision:
        summary = self.audit.verification_status_summary(task_id)
        reasons = self.audit.verification_review_reasons(summary)
        return WorkflowDecision(
            node="record_verification_risk_node",
            reason=",".join(reasons) or "verification_review_required",
            message="校验结果存在冲突、被排除事实或证据不足，报告结论必须保持审慎。",
            task_id=task_id,
            status_counts=summary,
        )

    def verification_review_required(self, task_id: str) -> bool:
        return self.audit.verification_review_required(task_id)

    def analyze_risks(
        self,
        *,
        task_id: str,
        record_decision: bool = True,
    ) -> tuple[str, WorkflowDecision | None]:
        task = self._task(task_id)
        facts = [
            ExtractedFactRead.model_validate(item) for item in self.artifacts.list_facts(task.id)
        ]
        verifications = [
            VerificationResultRead.model_validate(item)
            for item in self.artifacts.list_verifications(task.id)
        ]
        try:
            risk = self._analyze_risks_with_optional_stream(
                task_id=task.id,
                company_name=task.company_name,
                question=task.question,
                facts=facts,
                verifications=verifications,
            )
            return risk, None
        except Exception as exc:
            if self.settings.llm_provider != "mock":
                raise RuntimeError(
                    "LLM risk analysis failed while LLM_PROVIDER is non-mock; "
                    "aborting workflow."
                ) from exc
            logger.warning("Mock LLM risk analysis failed; using deterministic summary")
            decision = (
                WorkflowDecision(
                    node="analyze_risks_node",
                    reason="llm_risk_analysis_degraded",
                    message="LLM 风险分析失败，已改用规则摘要；报告不能超出已验证事实和证据缺口。",
                    task_id=task_id,
                )
                if record_decision
                else None
            )
            return (
                self._fallback_risk_analysis(
                    task=task,
                    facts=facts,
                    verification_results=verifications,
                ),
                decision,
            )

    def build_report(
        self,
        *,
        task_id: str,
        risk_analysis: str,
        retrieved_evidence: list[RetrievedEvidence],
        workflow_state: WorkflowState,
    ) -> ReportBuildResult:
        task = self._task(task_id)
        grounded_content, grounded_citations = (
            self.report_evidence.build_grounded_section_from_evidence(
                task=task,
                evidences=retrieved_evidence,
            )
        )
        source_quality_text = self.report_evidence.build_source_quality_summary(task.id)
        citations = self.report_evidence.merge_with_fact_citations(task.id, grounded_citations)

        report_schema = ReportAssemblyService(self.db, self.llm_provider).build_report(
            task=task,
            risk_analysis=risk_analysis,
            citations=citations,
        )
        verification_rows = self.artifacts.list_verifications(task.id)
        verified_ids = {
            item.fact_id for item in verification_rows if _verification_status_value(item) == "verified"
        }
        fact_rows = [
            ExtractedFactRead.model_validate(item)
            for item in self.artifacts.list_facts(task.id)
            if item.id in verified_ids
        ]
        chart_labels, chart_values = _chart_payload_from_facts(fact_rows)
        report_schema.content = append_charts_section(
            report_schema.content,
            labels=chart_labels,
            values=chart_values,
            title="关键指标趋势（示意）",
        )
        appendix_parts = [
            part.strip()
            for part in (
                source_quality_text,
                grounded_content,
                self.audit.build_workflow_audit_section(workflow_state).strip(),
            )
            if part and part.strip()
        ]
        if appendix_parts:
            report_schema.content = (
                report_schema.content
                + "\n\n### 材料与处理说明\n\n"
                + "\n\n".join(appendix_parts)
            )
        return ReportBuildResult(report=report_schema, citations=citations)

    def check_compliance(self, report: ReportCreate) -> ComplianceCheckOutcome:
        check = self.llm_provider.check_compliance(report.content)
        if check.status == ComplianceStatus.PASSED:
            report.compliance_status = check.status
            action: ComplianceAction = "passed"
        elif check.status == ComplianceStatus.REWRITTEN:
            action = "rewrite"
        elif check.status == ComplianceStatus.BLOCKED:
            action = "blocked"
        else:
            action = "passed"
        return ComplianceCheckOutcome(action=action, decision=check.model_dump(mode="json"))

    def apply_compliance_rewrite(
        self,
        *,
        report: ReportCreate,
        decision: dict[str, Any],
    ) -> ReportCreate:
        rewritten = decision.get("rewritten_text")
        if rewritten:
            report.content = rewritten
        report.compliance_status = ComplianceStatus.REWRITTEN
        return report

    def apply_blocked_compliance_result(
        self,
        *,
        report: ReportCreate,
        decision: dict[str, Any],
    ) -> ReportCreate:
        report.content = decision.get("rewritten_text") or _REPORT_BLOCKED_FALLBACK
        report.compliance_status = ComplianceStatus.BLOCKED
        return report

    def persist_report_and_complete_task(self, task_id: str, report: ReportCreate) -> None:
        self.artifacts.add_report(report)
        task = self._task(task_id)
        task.status = TaskStatusORM.COMPLETED
        task.error_message = None
        self.db.add(task)
        self.db.commit()

    def _task(self, task_id: str) -> ResearchTask:
        task = self.tasks.get(task_id)
        if task is None:
            raise ValueError("Task does not exist")
        return task

    _FINANCIAL_KEYWORD_RE = re.compile(
        r"研发|利润|收入|费用|资产|负债|现金流|净利|营收|成本|损益"
        r"|每股收益|毛利率|净利率|产能|产量|销量"
    )

    def _llm_ranked_extract(
        self,
        task: ResearchTask,
        chunk_reads: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        """正则粗筛 → Embedding 排序 → LLM 依次送检，意图命中即停。"""
        import math

        from app.services.question_intent import fact_matches_metric_family, parse_question_intent

        # Step A: 正则粗筛，chunk 必须包含财务关键词
        candidates = [ch for ch in chunk_reads if self._FINANCIAL_KEYWORD_RE.search(ch.text)]
        if not candidates:
            return []

        # Step B: Embedding 语义排序（复用 DashScope API）
        provider = self.report_evidence.embedding_provider
        query_vec = provider.embed_query(task.question)
        chunk_vecs = provider.embed_documents([ch.text for ch in candidates])

        scored = []
        for idx, cv in enumerate(chunk_vecs):
            dot = sum(a * b for a, b in zip(query_vec, cv))
            na = math.sqrt(sum(a * a for a in query_vec))
            nb = math.sqrt(sum(b * b for b in cv))
            score = float(dot / (na * nb)) if na > 0 and nb > 0 else 0.0
            scored.append((score, idx))
        scored.sort(key=lambda x: x[0], reverse=True)

        # Step C: 依次送 LLM，意图命中即停
        plan = parse_question_intent(task.question)
        max_attempts = 10
        all_llm_facts: list[ExtractedFactCreate] = []
        intent_matched = False

        for attempt, (score, idx) in enumerate(scored[:max_attempts]):
            chunk = candidates[idx]
            try:
                batch = self.llm_provider.extract_facts(
                    task_id=task.id,
                    company_name=task.company_name,
                    question=task.question,
                    chunks=[chunk],
                )
            except Exception:
                logger.warning("LLM extract failed for chunk %s (rank %d)", chunk.id, attempt + 1)
                continue

            for f in batch:
                all_llm_facts.append(f)

            if plan.strict_metrics and plan.metric_families:
                if any(
                    fact_matches_metric_family(f.metric_name, f.claim, plan.metric_families)
                    for f in batch
                ):
                    intent_matched = True
                    break
            elif batch:
                intent_matched = True
                break

        if intent_matched:
            logger.info(
                "LLM ranked extract: intent matched at chunk %d/%d (score=%.3f), "
                "total LLM facts=%d",
                attempt + 1, len(scored), score, len(all_llm_facts),
            )
        else:
            logger.info(
                "LLM ranked extract: no intent match after %d chunks, %d facts extracted",
                min(len(scored), max_attempts), len(all_llm_facts),
            )

        return all_llm_facts

    def _extract_facts_with_llm_fallback(
        self,
        *,
        task_id: str,
        company_name: str,
        question: str,
        chunks: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        try:
            return self.llm_provider.extract_facts(
                task_id=task_id,
                company_name=company_name,
                question=question,
                chunks=chunks,
            )
        except Exception as exc:
            raise RuntimeError(
                "LLM fact extraction failed while deterministic extraction produced no facts."
            ) from exc

    def _analyze_risks_with_optional_stream(
        self,
        *,
        task_id: str,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verifications: list[VerificationResultRead],
    ) -> str:
        from app.providers.llm.deepseek_provider import DeepSeekLLMProvider

        if self.settings.effective("llm_streaming_enabled") and isinstance(
            self.llm_provider, DeepSeekLLMProvider
        ):
            bus = get_workflow_event_bus()

            def on_token(token: str) -> None:
                bus.emit(task_id, "report.streaming", token=token)

            return self.llm_provider.analyze_risks_streaming(
                company_name=company_name,
                question=question,
                facts=facts,
                verification_results=verifications,
                on_token=on_token,
            )
        return self.llm_provider.analyze_risks(
            company_name=company_name,
            question=question,
            facts=facts,
            verification_results=verifications,
        )

    def _fallback_risk_analysis(
        self,
        *,
        task: ResearchTask,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
    ) -> str:
        counts: dict[str, int] = {}
        for item in verification_results:
            key = _verification_status_value(item)
            counts[key] = counts.get(key, 0) + 1
        fact_preview = "；".join(item.claim for item in facts[:5]) or "当前没有结构化事实"
        return (
            f"LLM 风险分析暂时不可用，系统已改用规则摘要。企业：{task.company_name}。"
            f"研究问题：{task.question}。已抽取事实 {len(facts)} 条。"
            f"校验统计：{_format_verification_counts(counts)}。事实预览：{fact_preview}。"
            "报告只能围绕已验证事实和证据缺口表达，不提供投资建议。"
        )
