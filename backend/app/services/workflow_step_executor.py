"""Service 引擎用的逐步执行器（legacy，回归兼容路径）。

默认路径使用 LangGraph。本模块保留是因为：
- 老脚本 / 老测试仍按 ``WORKFLOW_STEP_NAMES`` 顺序断言；
- 排查问题时偶尔切到 ``WORKFLOW_ENGINE=service`` 验证业务行为是否与图编排一致。

实现策略：所有 ``_xxx`` 业务方法不再重复实现，而是直接代理到 ``ResearchDomainServices``，
保证 service / langgraph 两条路径产出一致。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ResearchTask
from app.db.models import TaskStatus as TaskStatusORM
from app.providers.llm import LLMProvider
from app.providers.search import SearchProvider
from app.repositories import ResearchArtifactRepository
from app.schemas.common import ComplianceStatus
from app.schemas.report import ReportCreate
from app.schemas.workflow import WorkflowState, WorkflowStepResult
from app.services.research_domain import ResearchDomainServices
from app.services.workflow_audit import WorkflowAuditService

logger = logging.getLogger(__name__)


class WorkflowStepExecutor:
    """按 ``WORKFLOW_STEP_NAMES`` 顺序逐步执行。"""

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
        # 延迟构建 domain：测试用 SimpleNamespace 时不会触发，避免造一堆 mock。
        self._domain: ResearchDomainServices | None = None

    # ---------- 公共接口 ----------
    def execute_step(self, state: WorkflowState, step_name: str, fn: Callable[[], None]) -> None:
        """统一封装一步执行：记录起止时间与成功/失败。"""
        started = datetime.now(timezone.utc)
        state.current_step = step_name
        try:
            fn()
        except Exception as exc:
            state.steps.append(
                WorkflowStepResult(
                    step_name=step_name,
                    success=False,
                    error=str(exc),
                    started_at=started,
                    finished_at=datetime.now(timezone.utc),
                )
            )
            raise

        state.steps.append(
            WorkflowStepResult(
                step_name=step_name,
                success=True,
                message="ok",
                started_at=started,
                finished_at=datetime.now(timezone.utc),
            )
        )

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
            "CreateResearchTask": lambda: None,  # 任务由 caller 提前创建
            "CollectSources": lambda: self._domain_facade().collect_sources(task.id),
            "ChunkAndIndexSources": lambda: self._chunk_and_index(task),
            "ExtractFacts": lambda: self._domain_facade().extract_facts(task.id),
            "VerifyFacts": lambda: self._domain_facade().verify_facts(task.id),
            "AnalyzeRisks": lambda: self._analyze_risks(task, state),
            "GenerateReport": lambda: self._generate_report(task, state),
            "ComplianceCheck": lambda: self._compliance_check(state),
            "SaveResult": lambda: self._save_result(task, state),
        }
        action = step_actions.get(step_name)
        if action is None:
            raise ValueError(f"Unknown workflow step: {step_name}")
        self.execute_step(state, step_name, action)

    # ---------- 实际业务（全部委托给 domain） ----------
    def _domain_facade(self) -> ResearchDomainServices:
        if self._domain is None:
            self._domain = ResearchDomainServices(
                db=self.db,
                settings=self.settings,
                artifacts=self.artifacts,
                search_provider=self.search_provider,
                llm_provider=self.llm_provider,
                audit=self.audit,
            )
        return self._domain

    def _chunk_and_index(self, task: ResearchTask) -> None:
        domain = self._domain_facade()
        domain.ingest_chunks(task.id)
        domain.embed_chunks(task.id)

    def _analyze_risks(self, task: ResearchTask, state: WorkflowState) -> None:
        risk_text, decision = self._domain_facade().analyze_risks(task_id=task.id)
        if decision is not None:
            # 复用 audit 决策表，保持与 LangGraph 引擎一致的审计字段。
            self.audit.record_workflow_decision(
                state,
                node=decision.node,
                reason=decision.reason,
                message=decision.message,
                task_id=decision.task_id,
                status_counts=decision.status_counts,
            )
            state.errors.append(f"workflow_decision:{decision.reason}")
        state.intermediate_outputs["risk_analysis"] = risk_text

    def _generate_report(self, task: ResearchTask, state: WorkflowState) -> None:
        evidences = state.intermediate_outputs.get("retrieved_evidence", []) or []
        if not evidences:
            indexed_chunk_count = len(self.artifacts.list_chunks(task.id))
            evidences = self._domain_facade().retrieve_evidence(
                task_id=task.id,
                indexed_chunk_count=indexed_chunk_count,
            )
            state.intermediate_outputs["retrieved_evidence"] = evidences
        result = self._domain_facade().build_report(
            task_id=task.id,
            risk_analysis=str(state.intermediate_outputs.get("risk_analysis", "")),
            retrieved_evidence=evidences,
            workflow_state=state,
        )
        state.citations = result.citations
        state.intermediate_outputs["report"] = result.report.model_dump(mode="json")

    def _compliance_check(self, state: WorkflowState) -> None:
        report_payload = state.intermediate_outputs.get("report")
        if report_payload is None:
            raise ValueError("GenerateReport did not produce a report payload")

        report = ReportCreate.model_validate(report_payload)
        outcome = self._domain_facade().check_compliance(report)
        decision = outcome.decision
        violations = decision.get("violations") or []

        if outcome.action == "rewrite":
            self._domain_facade().apply_compliance_rewrite(report=report, decision=decision)
            state.errors.append(f"compliance_rewritten:{','.join(violations)}")
        elif outcome.action == "blocked":
            self._domain_facade().apply_blocked_compliance_result(
                report=report, decision=decision
            )
            state.errors.append(f"compliance_violation:{','.join(violations)}")
        elif outcome.action == "passed":
            report.compliance_status = ComplianceStatus.PASSED

        state.intermediate_outputs["report"] = report.model_dump(mode="json")
        state.intermediate_outputs["compliance"] = decision

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
