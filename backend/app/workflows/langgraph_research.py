from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.providers.llm import LLMProvider
from app.providers.search import SearchProvider
from app.repositories import ResearchArtifactRepository
from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.common import TaskStatus
from app.schemas.fact import ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.retrieval import RetrievedEvidence
from app.schemas.source import SourceRead
from app.schemas.verification import VerificationResultRead
from app.schemas.workflow import WorkflowDecision, WorkflowState, WorkflowStepResult
from app.services.research_domain import ComplianceAction, ResearchDomainServices
from app.services.workflow_audit import WorkflowAuditService

logger = logging.getLogger(__name__)


class ResearchGraphState(TypedDict, total=False):
    task_id: str
    company_name: str
    question: str
    sources: list[SourceRead]
    evidence_chunks: list[EvidenceChunkRead]
    embedding_results: list[dict[str, Any]]
    retrieved_evidence: list[RetrievedEvidence]
    extracted_facts: list[ExtractedFactRead]
    verification_results: list[VerificationResultRead]
    risk_analysis: str | None
    report: ReportCreate | None
    citations: list[Citation]
    compliance_decision: dict[str, Any] | None
    status: str
    error: str | None
    steps: list[WorkflowStepResult]
    workflow_decisions: list[WorkflowDecision]
    source_quality_summary: dict[str, Any]
    source_quality_insufficient: bool
    compliance_action: ComplianceAction | None


RESEARCH_GRAPH_REQUIRED_FIELDS = (
    "task_id",
    "company_name",
    "question",
    "sources",
    "evidence_chunks",
    "embedding_results",
    "retrieved_evidence",
    "extracted_facts",
    "verification_results",
    "risk_analysis",
    "report",
    "citations",
    "compliance_decision",
    "status",
    "error",
    "steps",
    "workflow_decisions",
    "source_quality_summary",
    "source_quality_insufficient",
    "compliance_action",
)

RESEARCH_GRAPH_NODE_NAMES = (
    # load -> collect -> quality gate
    "load_task_node",
    "collect_sources_node",
    "source_quality_gate_node",
    "record_source_quality_gap_node",
    # ingestion -> embedding -> retrieval
    "ingest_chunks_node",
    "embed_chunks_node",
    "retrieve_evidence_node",
    # fact pipeline and audit branches
    "extract_facts_node",
    "verify_facts_node",
    "record_evidence_gap_node",
    "record_verification_risk_node",
    # bounded LLM work, report assembly, compliance, persistence
    "analyze_risks_node",
    "build_report_node",
    "compliance_check_node",
    "apply_compliance_rewrite_node",
    "persist_result_node",
    "persist_blocked_result_node",
)


def initial_research_graph_state(task_id: str) -> ResearchGraphState:
    return {
        "task_id": task_id,
        "company_name": "",
        "question": "",
        "sources": [],
        "evidence_chunks": [],
        "embedding_results": [],
        "retrieved_evidence": [],
        "extracted_facts": [],
        "verification_results": [],
        "risk_analysis": None,
        "report": None,
        "citations": [],
        "compliance_decision": None,
        "status": TaskStatus.RUNNING.value,
        "error": None,
        "steps": [],
        "workflow_decisions": [],
        "source_quality_summary": {},
        "source_quality_insufficient": False,
        "compliance_action": None,
    }


class LangGraphWorkflowEngine:
    """Default workflow engine backed by LangGraph StateGraph."""

    def __init__(
        self,
        *,
        db: Session,
        settings: Settings,
        artifacts: ResearchArtifactRepository,
        search_provider: SearchProvider,
        llm_provider: LLMProvider,
        audit: WorkflowAuditService,
        domain_services: ResearchDomainServices | None = None,
    ) -> None:
        self.domain = domain_services or ResearchDomainServices(
            db=db,
            settings=settings,
            artifacts=artifacts,
            search_provider=search_provider,
            llm_provider=llm_provider,
            audit=audit,
        )
        self.graph = self._build_graph().compile()

    def run(self, task_id: str) -> WorkflowState:
        graph_state = initial_research_graph_state(task_id)
        try:
            graph_state = self.graph.invoke(graph_state)
        except Exception as exc:
            logger.exception("LangGraph research workflow failed: %s", exc)
            graph_state["status"] = TaskStatus.FAILED.value
            graph_state["error"] = str(exc)
        return self.to_workflow_state(graph_state)

    def get_status(self, task_id: str) -> WorkflowState | None:
        return self.domain.workflow_status(task_id)

    def resume(self, task_id: str) -> WorkflowState:
        return self.run(task_id)

    def to_workflow_state(self, graph_state: ResearchGraphState) -> WorkflowState:
        status_value = graph_state.get("status") or TaskStatus.FAILED.value
        try:
            status = TaskStatus(status_value)
        except ValueError:
            status = TaskStatus.FAILED
        errors = []
        if graph_state.get("error"):
            errors.append(str(graph_state["error"]))
        return WorkflowState(
            task_id=graph_state["task_id"],
            company_name=graph_state.get("company_name", ""),
            question=graph_state.get("question", ""),
            status=status,
            current_step=graph_state.get("steps", [])[-1].step_name
            if graph_state.get("steps")
            else None,
            steps=graph_state.get("steps", []),
            citations=graph_state.get("citations", []),
            workflow_decisions=graph_state.get("workflow_decisions", []),
            intermediate_outputs={
                "risk_analysis": graph_state.get("risk_analysis"),
                "report": graph_state.get("report").model_dump(mode="json")
                if graph_state.get("report") is not None
                else None,
                "compliance": graph_state.get("compliance_decision"),
                "source_quality_summary": graph_state.get("source_quality_summary"),
                "retrieved_evidence_count": len(graph_state.get("retrieved_evidence", [])),
            },
            errors=errors,
        )

    def _build_graph(self) -> StateGraph:
        # LangGraph owns orchestration only; business work stays in domain services.
        graph = StateGraph(ResearchGraphState)
        for node_name in RESEARCH_GRAPH_NODE_NAMES:
            graph.add_node(node_name, getattr(self, node_name))

        graph.add_edge(START, "load_task_node")
        graph.add_edge("load_task_node", "collect_sources_node")
        graph.add_edge("collect_sources_node", "source_quality_gate_node")
        graph.add_conditional_edges(
            "source_quality_gate_node",
            self._route_source_quality,
            {
                "insufficient": "record_source_quality_gap_node",
                "sufficient": "ingest_chunks_node",
            },
        )
        graph.add_edge("record_source_quality_gap_node", "ingest_chunks_node")
        graph.add_edge("ingest_chunks_node", "embed_chunks_node")
        graph.add_edge("embed_chunks_node", "retrieve_evidence_node")
        graph.add_edge("retrieve_evidence_node", "extract_facts_node")
        graph.add_conditional_edges(
            "extract_facts_node",
            self._route_after_fact_extraction,
            {
                "has_facts": "verify_facts_node",
                "no_facts": "record_evidence_gap_node",
            },
        )
        graph.add_conditional_edges(
            "verify_facts_node",
            self._route_after_verification,
            {
                "review_required": "record_verification_risk_node",
                "clear": "analyze_risks_node",
            },
        )
        graph.add_edge("record_evidence_gap_node", "analyze_risks_node")
        graph.add_edge("record_verification_risk_node", "analyze_risks_node")
        graph.add_edge("analyze_risks_node", "build_report_node")
        graph.add_edge("build_report_node", "compliance_check_node")
        graph.add_conditional_edges(
            "compliance_check_node",
            self._route_after_compliance,
            {
                "passed": "persist_result_node",
                "rewrite": "apply_compliance_rewrite_node",
                "blocked": "persist_blocked_result_node",
            },
        )
        graph.add_edge("apply_compliance_rewrite_node", "persist_result_node")
        graph.add_edge("persist_result_node", END)
        graph.add_edge("persist_blocked_result_node", END)
        return graph

    def load_task_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            task = self.domain.load_task(state["task_id"])
            state["company_name"] = task.company_name
            state["question"] = task.question

        return self._execute_node(state, "load_task_node", action)

    def collect_sources_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            state["sources"] = self.domain.collect_sources(state["task_id"])

        return self._execute_node(state, "collect_sources_node", action)

    def source_quality_gate_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            result = self.domain.evaluate_source_quality(state["task_id"])
            state["source_quality_summary"] = result.summary
            state["source_quality_insufficient"] = result.insufficient

        return self._execute_node(state, "source_quality_gate_node", action)

    def record_source_quality_gap_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            state.setdefault("workflow_decisions", []).append(
                self.domain.record_source_quality_gap(state["task_id"])
            )

        return self._execute_node(state, "record_source_quality_gap_node", action)

    def ingest_chunks_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            state["evidence_chunks"] = self.domain.ingest_chunks(state["task_id"])

        return self._execute_node(state, "ingest_chunks_node", action)

    def embed_chunks_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            result = self.domain.embed_chunks(state["task_id"])
            state["embedding_results"] = result.embedding_results
            state["evidence_chunks"] = result.evidence_chunks

        return self._execute_node(state, "embed_chunks_node", action)

    def retrieve_evidence_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            state["retrieved_evidence"] = self.domain.retrieve_evidence(
                task_id=state["task_id"],
                indexed_chunk_count=len(state.get("embedding_results", [])),
            )

        return self._execute_node(state, "retrieve_evidence_node", action)

    def extract_facts_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            state["extracted_facts"] = self.domain.extract_facts(state["task_id"])

        return self._execute_node(state, "extract_facts_node", action)

    def verify_facts_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            state["verification_results"] = self.domain.verify_facts(state["task_id"])

        return self._execute_node(state, "verify_facts_node", action)

    def record_evidence_gap_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            state.setdefault("workflow_decisions", []).append(
                self.domain.record_evidence_gap(state["task_id"])
            )

        return self._execute_node(state, "record_evidence_gap_node", action)

    def record_verification_risk_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            state.setdefault("workflow_decisions", []).append(
                self.domain.record_verification_risk(state["task_id"])
            )

        return self._execute_node(state, "record_verification_risk_node", action)

    def analyze_risks_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            risk_analysis, decision = self.domain.analyze_risks(task_id=state["task_id"])
            state["risk_analysis"] = risk_analysis
            if decision is not None:
                state.setdefault("workflow_decisions", []).append(decision)

        return self._execute_node(state, "analyze_risks_node", action)

    def build_report_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            result = self.domain.build_report(
                task_id=state["task_id"],
                risk_analysis=str(state.get("risk_analysis") or ""),
                retrieved_evidence=state.get("retrieved_evidence", []),
                workflow_state=self.to_workflow_state(state),
            )
            state["citations"] = result.citations
            state["report"] = result.report

        return self._execute_node(state, "build_report_node", action)

    def compliance_check_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            report = state.get("report")
            if report is None:
                raise ValueError("build_report_node did not produce a report")
            outcome = self.domain.check_compliance(report)
            state["compliance_decision"] = outcome.decision
            state["compliance_action"] = outcome.action

        return self._execute_node(state, "compliance_check_node", action)

    def apply_compliance_rewrite_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            report = self._report(state)
            decision = state.get("compliance_decision") or {}
            state["report"] = self.domain.apply_compliance_rewrite(
                report=report,
                decision=decision,
            )

        return self._execute_node(state, "apply_compliance_rewrite_node", action)

    def persist_result_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            self.domain.persist_report_and_complete_task(state["task_id"], self._report(state))
            state["status"] = TaskStatus.COMPLETED.value

        return self._execute_node(state, "persist_result_node", action)

    def persist_blocked_result_node(self, state: ResearchGraphState) -> ResearchGraphState:
        def action() -> None:
            report = self._report(state)
            decision = state.get("compliance_decision") or {}
            blocked_report = self.domain.apply_blocked_compliance_result(
                report=report,
                decision=decision,
            )
            state["report"] = blocked_report
            self.domain.persist_report_and_complete_task(state["task_id"], blocked_report)
            state["status"] = TaskStatus.COMPLETED.value

        return self._execute_node(state, "persist_blocked_result_node", action)

    def _execute_node(
        self,
        state: ResearchGraphState,
        step_name: str,
        fn: Callable[[], None],
    ) -> ResearchGraphState:
        started = datetime.now(timezone.utc)
        try:
            fn()
            state.setdefault("steps", []).append(
                WorkflowStepResult(
                    step_name=step_name,
                    success=True,
                    message="ok",
                    started_at=started,
                    finished_at=datetime.now(timezone.utc),
                )
            )
        except Exception as exc:
            state["status"] = TaskStatus.FAILED.value
            state["error"] = str(exc)
            state.setdefault("steps", []).append(
                WorkflowStepResult(
                    step_name=step_name,
                    success=False,
                    error=str(exc),
                    started_at=started,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            raise
        return state

    def _route_source_quality(self, state: ResearchGraphState) -> str:
        return "insufficient" if state.get("source_quality_insufficient") else "sufficient"

    def _route_after_fact_extraction(self, state: ResearchGraphState) -> str:
        return "has_facts" if state.get("extracted_facts") else "no_facts"

    def _route_after_verification(self, state: ResearchGraphState) -> str:
        return (
            "review_required"
            if self.domain.verification_review_required(state["task_id"])
            else "clear"
        )

    def _route_after_compliance(self, state: ResearchGraphState) -> ComplianceAction:
        return state.get("compliance_action") or "blocked"

    def _report(self, state: ResearchGraphState) -> ReportCreate:
        report = state.get("report")
        if report is None:
            raise ValueError("report is missing from graph state")
        return report


LangGraphResearchWorkflow = LangGraphWorkflowEngine
