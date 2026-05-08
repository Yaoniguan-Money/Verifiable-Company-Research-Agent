"""Legacy service workflow fallback.

Default orchestration is LangGraph. This executor is kept for WORKFLOW_ENGINE=service
compatibility during the migration window and should not own new main-flow behavior.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.init_db import ensure_lightweight_schema_updates
from app.db.models import (
    EvidenceChunk,
    ExtractedFact,
    ResearchTask,
    VerificationResult,
)
from app.db.models import TaskStatus as TaskStatusORM
from app.providers.llm import LLMProvider
from app.providers.search import SearchProvider
from app.repositories import ResearchArtifactRepository
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.common import ComplianceStatus
from app.schemas.fact import ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.verification import VerificationResultRead
from app.schemas.workflow import WorkflowState, WorkflowStepResult
from app.services.fact_extraction import FactExtractionService
from app.services.fact_verification import FactVerificationService
from app.services.ingestion import IngestionService
from app.services.report_assembly import ReportAssemblyService
from app.services.report_evidence import ReportEvidenceService
from app.services.workflow_audit import WorkflowAuditService

logger = logging.getLogger(__name__)


class WorkflowStepExecutor:
    WORKFLOW_STEP_NAMES = (
        "CreateResearchTask",
        "CollectSources",
        "ChunkAndIndexSources",
        "ExtractFacts",
        "VerifyFacts",
        "AnalyzeRisks",
        "GenerateReport",
        "ComplianceCheck",
        "SaveResult",
    )

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
        self.search_provider = search_provider
        self.llm_provider = llm_provider
        self.audit = audit

    def execute_step(self, state: WorkflowState, step_name: str, fn: Callable[[], None]) -> None:
        started = datetime.now(timezone.utc)
        state.current_step = step_name
        try:
            fn()
            step = WorkflowStepResult(
                step_name=step_name,
                success=True,
                message="ok",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )
            state.steps.append(step)
        except Exception as exc:
            step = WorkflowStepResult(
                step_name=step_name,
                success=False,
                error=str(exc),
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )
            state.steps.append(step)
            raise

    def run_service_workflow_steps(self, task: ResearchTask, state: WorkflowState) -> None:
        for step_name in self.WORKFLOW_STEP_NAMES:
            self.execute_workflow_step(task=task, state=state, step_name=step_name)

    def execute_workflow_step(
        self,
        *,
        task: ResearchTask,
        state: WorkflowState,
        step_name: str,
    ) -> None:
        step_actions: dict[str, Callable[[], None]] = {
            "CreateResearchTask": lambda: None,
            "CollectSources": lambda: self._collect_sources(task),
            "ChunkAndIndexSources": lambda: self._chunk_and_index_sources(task),
            "ExtractFacts": lambda: self._extract_facts(task),
            "VerifyFacts": lambda: self._verify_facts(task),
            "AnalyzeRisks": lambda: self._analyze_risks(task, state),
            "GenerateReport": lambda: self._generate_report(task, state),
            "ComplianceCheck": lambda: self._compliance_check(state),
            "SaveResult": lambda: self._save_result(task, state),
        }
        action = step_actions.get(step_name)
        if action is None:
            raise ValueError(f"Unknown workflow step: {step_name}")
        self.execute_step(state, step_name, action)

    def _collect_sources(self, task: ResearchTask) -> None:
        source_schemas = self.search_provider.search(task.company_name, task.question)
        self.artifacts.add_sources(task_id=task.id, sources=source_schemas)
        self.db.commit()

    def _chunk_and_index_sources(self, task: ResearchTask) -> None:
        sources = self.artifacts.list_sources(task.id)
        ingestion = IngestionService(self.db)
        for source in sources:
            ingestion.ingest_chunks_for_source(
                task.id,
                source.id,
                chunk_size=self.settings.workflow_chunk_size,
                chunk_overlap=self.settings.workflow_chunk_overlap,
            )
        self.db.commit()

    def _extract_facts(self, task: ResearchTask) -> None:
        chunk_rows = self.artifacts.list_chunks(task.id)
        chunk_reads = [self._to_chunk_read(row) for row in chunk_rows]
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

    def _verify_facts(self, task: ResearchTask) -> None:
        fact_rows = self.artifacts.list_facts(task.id)
        if not fact_rows:
            return

        fact_reads = [ExtractedFactRead.model_validate(item) for item in fact_rows]
        output = FactVerificationService().verify_facts(
            task_id=task.id,
            facts=fact_reads,
            source_context=self.artifacts.source_context(task.id),
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

    def _analyze_risks(self, task: ResearchTask, state: WorkflowState) -> None:
        facts = self.artifacts.list_facts(task.id)
        verifications = self.artifacts.list_verifications(task.id)
        fact_reads = [ExtractedFactRead.model_validate(item) for item in facts]
        verification_reads = [VerificationResultRead.model_validate(item) for item in verifications]
        try:
            risk_text = self.llm_provider.analyze_risks(
                company_name=task.company_name,
                question=task.question,
                facts=fact_reads,
                verification_results=verification_reads,
            )
        except Exception as exc:
            if self.settings.llm_provider != "mock":
                raise RuntimeError(
                    "LLM risk analysis failed while LLM_PROVIDER is non-mock; aborting workflow."
                ) from exc
            logger.warning("LLM risk analysis failed; falling back to deterministic summary", exc_info=True)
            state.errors.append("llm_risk_analysis_degraded")
            self.audit.record_workflow_decision(
                state,
                node="AnalyzeRisks",
                reason="llm_risk_analysis_degraded",
                message="LLM 风险分析失败，已降级为规则摘要；报告不应形成超出证据链的确定性结论。",
                task_id=task.id,
            )
            risk_text = self._fallback_risk_analysis(
                task=task,
                facts=fact_reads,
                verification_results=verification_reads,
            )
        state.intermediate_outputs["risk_analysis"] = risk_text

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
        fact_preview = "；".join(item.claim for item in facts[:5]) or "当前未抽取到结构化事实"
        return (
            f"LLM 风险分析暂时不可用，系统已降级为规则摘要。企业：{task.company_name}。"
            f"研究问题：{task.question}。已抽取事实 {len(facts)} 条，验证状态统计：{counts or {'none': 0}}。"
            f"事实摘要：{fact_preview}。风险观察应以已验证事实为主；对冲突或证据不足的事实只做信息缺口提示，"
            "不形成确定性结论，也不提供投资建议。"
        )

    def _generate_report(self, task: ResearchTask, state: WorkflowState) -> None:
        evidence = ReportEvidenceService(self.db)
        grounded_content, grounded_citations = self._build_grounded_section(task)
        source_quality_summary = evidence.build_source_quality_summary(task.id)
        citations = evidence.merge_with_fact_citations(task.id, grounded_citations)
        state.citations = citations

        report_schema = ReportAssemblyService(self.db, self.llm_provider).build_report(
            task=task,
            risk_analysis=str(state.intermediate_outputs.get("risk_analysis", "")),
            citations=citations,
        )
        report_schema.content = (
            report_schema.content
            + "\n\n"
            + source_quality_summary
            + "\n\n## 证据摘要（Grounded）\n"
            + grounded_content
            + self.audit.build_workflow_audit_section(state)
        )
        state.intermediate_outputs["grounded_section"] = grounded_content
        state.intermediate_outputs["report"] = report_schema.model_dump(mode="json")

    def _build_grounded_section(self, task: ResearchTask) -> tuple[str, list[Citation]]:
        return ReportEvidenceService(self.db).build_grounded_section(task)

    def _compliance_check(self, state: WorkflowState) -> None:
        report_payload = state.intermediate_outputs.get("report")
        if report_payload is None:
            raise ValueError("GenerateReport did not produce a report payload")

        report = ReportCreate.model_validate(report_payload)
        check = self.llm_provider.check_compliance(report.content)
        if check.status == ComplianceStatus.PASSED:
            report.compliance_status = check.status
        elif check.status == ComplianceStatus.REWRITTEN:
            # 4.D 最小接入：报告输出层改写，避免直接暴露违规表达。
            report.content = check.rewritten_text or report.content
            report.compliance_status = check.status
            state.errors.append(f"compliance_rewritten:{','.join(check.violations)}")
        elif check.status == ComplianceStatus.BLOCKED:
            # 4.D 最小接入：报告输出层拒绝，给出可继续查询的合规方向。
            report.content = check.rewritten_text or (
                "当前请求涉及投资建议导向内容，已按合规策略拒绝输出。"
                "你可以继续询问企业经营、财务变化、信息披露与风险分析。"
            )
            report.compliance_status = check.status
            state.errors.append(f"compliance_violation:{','.join(check.violations)}")
        else:
            report.compliance_status = check.status

        state.intermediate_outputs["report"] = report.model_dump(mode="json")
        state.intermediate_outputs["compliance"] = check.model_dump(mode="json")

    def _save_result(self, task: ResearchTask, state: WorkflowState) -> None:
        report_payload = state.intermediate_outputs.get("report")
        if report_payload is None:
            raise ValueError("ComplianceCheck did not leave a report payload")
        report = ReportCreate.model_validate(report_payload)

        self.artifacts.add_report(report)
        task.status = TaskStatusORM.COMPLETED
        task.error_message = None
        self.db.add(task)
        self.db.commit()

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
