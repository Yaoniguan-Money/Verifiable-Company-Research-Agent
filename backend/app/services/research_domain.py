from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.init_db import ensure_lightweight_schema_updates
from app.db.models import EvidenceChunk, ExtractedFact, ResearchTask, VerificationResult
from app.db.models import TaskStatus as TaskStatusORM
from app.providers.llm import LLMProvider
from app.providers.search import SearchProvider
from app.repositories import ResearchArtifactRepository, ResearchTaskRepository
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.common import (
    ComplianceStatus,
    source_quality_counts,
    source_quality_insufficient,
)
from app.schemas.fact import ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.retrieval import RetrievedEvidence
from app.schemas.source import SourceRead
from app.schemas.verification import VerificationResultRead
from app.schemas.workflow import WorkflowDecision, WorkflowState
from app.services.fact_extraction import FactExtractionService
from app.services.fact_verification import FactVerificationService
from app.services.ingestion import IngestionService
from app.services.report_assembly import ReportAssemblyService
from app.services.report_evidence import ReportEvidenceService
from app.services.workflow_audit import WorkflowAuditService

logger = logging.getLogger(__name__)

ComplianceAction = Literal["passed", "rewrite", "blocked"]


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


class ResearchDomainServices:
    """Business capabilities used by workflow nodes.

    Nodes keep graph state and branching logic; this service owns provider calls,
    evidence rules, report grounding, and artifact persistence for each step.
    """

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
        ingestion = IngestionService(self.db)
        for source in self.artifacts.list_sources(task_id):
            ingestion.ingest_chunks_for_source(
                task_id,
                source.id,
                chunk_size=self.settings.workflow_chunk_size,
                chunk_overlap=self.settings.workflow_chunk_overlap,
            )
        self.db.commit()
        return [self._to_chunk_read(item) for item in self.artifacts.list_chunks(task_id)]

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
            evidence_chunks=[
                self._to_chunk_read(item) for item in self.artifacts.list_chunks(task_id)
            ],
        )

    def retrieve_evidence(
        self,
        *,
        task_id: str,
        indexed_chunk_count: int,
    ) -> list[RetrievedEvidence]:
        task = self._task(task_id)
        return self.report_evidence.retrieve_evidence_for_task(
            task=task,
            indexed_chunk_count=indexed_chunk_count,
        )

    def extract_facts(self, task_id: str) -> list[ExtractedFactRead]:
        task = self._task(task_id)
        chunk_reads = [self._to_chunk_read(row) for row in self.artifacts.list_chunks(task.id)]
        extraction = FactExtractionService().extract_from_chunks(
            task_id=task.id,
            company_name=task.company_name,
            question=task.question,
            chunks=chunk_reads,
        )
        facts = [
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
            for item in extraction.facts
        ]
        self.artifacts.add_facts(facts)
        self.db.commit()
        return [ExtractedFactRead.model_validate(item) for item in self.artifacts.list_facts(task.id)]

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
            message=(
                "Fact extraction produced no structured facts; verification is skipped "
                "and the report should describe an evidence gap."
            ),
            task_id=task_id,
        )

    def record_verification_risk(self, task_id: str) -> WorkflowDecision:
        summary = self.audit.verification_status_summary(task_id)
        reasons = self.audit.verification_review_reasons(summary)
        return WorkflowDecision(
            node="record_verification_risk_node",
            reason=",".join(reasons) or "verification_review_required",
            message=(
                "Verification results include conflicts, rejected facts, or only "
                "insufficient facts; report conclusions must stay cautious."
            ),
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
        facts = [ExtractedFactRead.model_validate(item) for item in self.artifacts.list_facts(task.id)]
        verifications = [
            VerificationResultRead.model_validate(item)
            for item in self.artifacts.list_verifications(task.id)
        ]
        try:
            return (
                self.llm_provider.analyze_risks(
                    company_name=task.company_name,
                    question=task.question,
                    facts=facts,
                    verification_results=verifications,
                ),
                None,
            )
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
                    message="Risk analysis degraded to deterministic summary in mock mode.",
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
        report_schema.content = (
            report_schema.content
            + "\n\n"
            + source_quality_text
            + "\n\n## 证据摘要（Grounded）\n"
            + grounded_content
            + self.audit.build_workflow_audit_section(workflow_state)
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
        return ComplianceCheckOutcome(
            action=action,
            decision=check.model_dump(mode="json"),
        )

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
        report.content = decision.get("rewritten_text") or (
            "当前请求涉及投资建议导向内容，已按合规策略拒绝输出。"
            "你可以继续查询企业经营、财务变化、信息披露与风险分析。"
        )
        report.compliance_status = ComplianceStatus.BLOCKED
        return report

    def persist_report_and_complete_task(self, task_id: str, report: ReportCreate) -> None:
        self.artifacts.add_report(report)
        task = self._task(task_id)
        task.status = TaskStatusORM.COMPLETED
        task.error_message = None
        self.db.add(task)
        self.db.commit()

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

    def _task(self, task_id: str) -> ResearchTask:
        task = self.tasks.get(task_id)
        if task is None:
            raise ValueError("Task does not exist")
        return task

    def _to_chunk_read(self, chunk: EvidenceChunk) -> EvidenceChunkRead:
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

    def _fallback_risk_analysis(
        self,
        *,
        task: ResearchTask,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
    ) -> str:
        counts: dict[str, int] = {}
        for item in verification_results:
            key = getattr(item.status, "value", str(item.status))
            counts[key] = counts.get(key, 0) + 1
        fact_preview = "; ".join(item.claim for item in facts[:5]) or "no structured facts"
        return (
            f"LLM risk analysis is unavailable in mock mode. Company: {task.company_name}. "
            f"Question: {task.question}. Extracted facts: {len(facts)}. "
            f"Verification summary: {counts or {'none': 0}}. Fact preview: {fact_preview}. "
            "The report should stay within verified facts and evidence gaps, without "
            "investment advice."
        )
