"""研究任务生命周期门面服务。

负责：
- 任务 CRUD：``create_research_task``、``get_research_task``、``list_research_tasks``
- 执行控制：``run_workflow``（含原子 claim、失败回写、状态序列化）
- 副产物读写：sources / facts / verifications / report
- 追问入口：``chat_with_task``

具体业务（搜索、嵌入、检索、合规、报告组装）下沉到对应 service / workflow engine。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.init_db import get_default_user
from app.db.models import (
    ExtractedFact,
    ResearchTask,
    Source,
    VerificationResult,
)
from app.db.models import TaskStatus as TaskStatusORM
from app.providers.factory import ProviderFactory
from app.providers.llm import LLMProvider
from app.providers.search import SearchProvider
from app.repositories import ResearchArtifactRepository, ResearchTaskRepository
from app.schemas.common import TaskStatus
from app.schemas.report import ReportRead
from app.schemas.workflow import WorkflowState
from app.services.chat import ChatService
from app.services.report_output import ReportOutputService
from app.services.workflow_audit import WorkflowAuditService
from app.workflows.base import WorkflowEngine
from app.workflows.langgraph_research import LangGraphWorkflowEngine
from app.workflows.service_engine import ServiceWorkflowEngine

logger = logging.getLogger(__name__)


@dataclass
class RunWorkflowResult:
    """``run_workflow`` 的返回结构。

    - ``state``：完整的 WorkflowState，包含 steps / errors / intermediate outputs。
    - ``summary``：报告内容前 200 字（用于异步运行时快速回显）。
    """

    success: bool
    task_id: str
    report_id: str | None
    title: str | None
    summary: str | None
    error: str | None
    state: WorkflowState


_SUMMARY_PREVIEW_CHARS = 200


class WorkflowFacade:
    """对外暴露的研究任务门面。"""

    # 只有 CREATED / FAILED 的任务允许重新触发，避免并发重复跑同一任务。
    RUNNABLE_STATUSES = (TaskStatusORM.CREATED, TaskStatusORM.FAILED)

    def __init__(
        self,
        db: Session,
        search_provider: SearchProvider | None = None,
        llm_provider: LLMProvider | None = None,
        workflow_engine: WorkflowEngine | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        providers = ProviderFactory(self.settings)
        self.search_provider = search_provider or providers.create_search_provider()
        self.llm_provider = llm_provider or providers.create_llm_provider()
        self.tasks = ResearchTaskRepository(db)
        self.artifacts = ResearchArtifactRepository(db)
        self.audit = WorkflowAuditService(self.artifacts)
        self.workflow_engine = workflow_engine or self._create_workflow_engine()

    # ---------- 任务 CRUD ----------
    def create_research_task(
        self,
        company_name: str,
        question: str,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> ResearchTask:
        if user_id is None:
            user_id = get_default_user(self.db).id

        if session_id is not None and not self.tasks.session_belongs_to_user(
            session_id=session_id, user_id=user_id
        ):
            raise ValueError("Session does not exist or does not belong to the user")

        return self.tasks.create(
            user_id=user_id,
            session_id=session_id,
            company_name=company_name,
            question=question,
        )

    def get_research_task(self, task_id: str) -> ResearchTask | None:
        return self.tasks.get(task_id)

    def list_research_tasks(self, *, limit: int = 50) -> list[ResearchTask]:
        return self.tasks.list_recent(limit=limit)

    # ---------- 执行 ----------
    def run_workflow(self, task_id: str) -> RunWorkflowResult:
        task = self.get_research_task(task_id)
        if task is None:
            raise ValueError("Task does not exist")

        # 原子 claim：把 created/failed → running，并发场景下保证只有一个 caller 成功。
        claimed_task = self._claim_task_for_run(task_id)
        if claimed_task is None:
            current = self.get_research_task(task_id) or task
            return self._not_claimable_result(task_id=task_id, task=current)

        task = claimed_task
        try:
            self._prepare_task_for_run(task)
            state = self.workflow_engine.run(task.id)
            if state.status == TaskStatus.FAILED:
                err = state.errors[-1] if state.errors else "Workflow failed"
                self._persist_workflow_failure(task_id, RuntimeError(err))
                return self._failure_result(task_id=task_id, error=err, state=state)
        except Exception as exc:  # 业务/底层异常都按失败处理，并把任务回写 FAILED。
            logger.exception("Workflow failed: %s", exc)
            err = self._persist_workflow_failure(task_id, exc)
            state = WorkflowState(
                task_id=task_id,
                company_name=task.company_name,
                question=task.question,
                status=TaskStatus.FAILED,
                errors=[err],
            )
            return self._failure_result(task_id=task_id, error=err, state=state)

        return self._success_result(task_id=task_id, state=state)

    def get_workflow_status(self, task_id: str) -> WorkflowState | None:
        return self.workflow_engine.get_status(task_id)

    def resume_workflow(self, task_id: str) -> RunWorkflowResult:
        state = self.workflow_engine.resume(task_id)
        return RunWorkflowResult(
            success=state.status != TaskStatus.FAILED,
            task_id=task_id,
            report_id=None,
            title=None,
            summary=None,
            error=state.errors[-1] if state.errors else None,
            state=state,
        )

    # ---------- 下游读取 ----------
    def get_report(self, task_id: str) -> ReportRead | None:
        return ReportOutputService(self.db, self.llm_provider).get_report(task_id)

    def get_report_for_output(self, task_id: str) -> ReportRead | None:
        """对外暴露报告时必须走这个接口，以确保 final compliance 兜底已生效。"""
        return ReportOutputService(self.db, self.llm_provider).get_report_for_output(task_id)

    def chat_with_task(self, *, task_id: str, message: str) -> dict[str, object]:
        result = ChatService(self.db, self.llm_provider).chat_with_task(
            task_id=task_id,
            message=message,
        )
        return {
            "task_id": result.task_id,
            "message": result.message,
            "answer": result.answer,
            "compliance_status": result.compliance_status,
            "violations": result.violations,
        }

    def list_sources(self, task_id: str) -> list[Source]:
        return self.artifacts.list_sources(task_id)

    def list_extracted_facts(self, task_id: str) -> list[ExtractedFact]:
        return self.artifacts.list_facts(task_id)

    def list_verification_results(self, task_id: str) -> list[VerificationResult]:
        return self.artifacts.list_verifications(task_id)

    # ---------- 内部辅助 ----------
    def _create_workflow_engine(self) -> WorkflowEngine:
        kwargs = {
            "db": self.db,
            "settings": self.settings,
            "artifacts": self.artifacts,
            "search_provider": self.search_provider,
            "llm_provider": self.llm_provider,
            "audit": self.audit,
        }
        if self.settings.workflow_engine == "langgraph":
            return LangGraphWorkflowEngine(**kwargs)
        return ServiceWorkflowEngine(**kwargs)

    def _claim_task_for_run(self, task_id: str) -> ResearchTask | None:
        return self.tasks.claim_for_run(
            task_id=task_id,
            runnable_statuses=self.RUNNABLE_STATUSES,
        )

    def _prepare_task_for_run(self, task: ResearchTask) -> None:
        """重跑前清掉旧产物，避免引用陈旧 sources / facts。"""
        self.artifacts.delete_task_outputs(task.id)
        self.db.commit()
        self.db.refresh(task)

    def _persist_workflow_failure(self, task_id: str, exc: Exception) -> str:
        """把任务标记为 FAILED 并清掉中间产物。出现二次异常时也保证返回错误描述。"""
        root_msg = str(exc)
        self.db.rollback()
        try:
            task_again = self.get_research_task(task_id)
            if task_again is not None:
                self.artifacts.delete_task_outputs(task_id)
                task_again.status = TaskStatusORM.FAILED
                task_again.error_message = root_msg
                self.db.add(task_again)
                self.db.commit()
            return root_msg
        except Exception as persist_exc:  # 持久化失败时也别让上层崩溃。
            logger.exception("Unable to persist failed task state: %s", persist_exc)
            self.db.rollback()
            return f"{root_msg} | unable to persist failed task state: {persist_exc}"

    def _not_claimable_result(self, *, task_id: str, task: ResearchTask) -> RunWorkflowResult:
        return RunWorkflowResult(
            success=False,
            task_id=task_id,
            report_id=None,
            title=None,
            summary=None,
            error=f"Task status is {task.status}; only created or failed tasks can run",
            state=WorkflowState(
                task_id=task_id,
                company_name=task.company_name,
                question=task.question,
                status=TaskStatus.FAILED,
            ),
        )

    def _failure_result(
        self, *, task_id: str, error: str, state: WorkflowState
    ) -> RunWorkflowResult:
        return RunWorkflowResult(
            success=False,
            task_id=task_id,
            report_id=None,
            title=None,
            summary=None,
            error=error,
            state=state,
        )

    def _success_result(self, *, task_id: str, state: WorkflowState) -> RunWorkflowResult:
        report_row = self.artifacts.get_report_by_task_id(task_id)
        report_id = report_row.id if report_row else None
        report_title = report_row.title if report_row else None
        summary_text: str | None = None
        if report_row and report_row.content:
            raw = report_row.content.strip()
            if len(raw) > _SUMMARY_PREVIEW_CHARS:
                summary_text = raw[:_SUMMARY_PREVIEW_CHARS] + "..."
            else:
                summary_text = raw
        return RunWorkflowResult(
            success=True,
            task_id=task_id,
            report_id=report_id,
            title=report_title,
            summary=summary_text,
            error=None,
            state=state,
        )


# 向后兼容：旧路由与测试仍按这个名字导入。
ResearchWorkflowService = WorkflowFacade
