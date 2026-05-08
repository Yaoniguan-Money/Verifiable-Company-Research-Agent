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
    success: bool
    task_id: str
    report_id: str | None
    title: str | None
    summary: str | None
    error: str | None
    state: WorkflowState


class WorkflowFacade:
    """Application service for task lifecycle, status, and workflow execution."""

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

    def create_research_task(
        self,
        company_name: str,
        question: str,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> ResearchTask:
        if user_id is None:
            user = get_default_user(self.db)
            user_id = user.id

        if session_id is not None:
            if not self.tasks.session_belongs_to_user(session_id=session_id, user_id=user_id):
                raise ValueError("Session does not exist or does not belong to the user")

        return self.tasks.create(
            user_id=user_id,
            session_id=session_id,
            company_name=company_name,
            question=question,
        )

    def get_research_task(self, task_id: str) -> ResearchTask | None:
        return self.tasks.get(task_id)

    def run_workflow(self, task_id: str) -> RunWorkflowResult:
        task = self.get_research_task(task_id)
        if task is None:
            raise ValueError("Task does not exist")

        claimed_task = self._claim_task_for_run(task_id)
        if claimed_task is None:
            current = self.get_research_task(task_id) or task
            return RunWorkflowResult(
                success=False,
                task_id=task_id,
                report_id=None,
                title=None,
                summary=None,
                error=(
                    f"Task status is {current.status}; only created or failed tasks can run"
                ),
                state=WorkflowState(
                    task_id=task_id,
                    company_name=current.company_name,
                    question=current.question,
                    status=TaskStatus.FAILED,
                ),
            )

        task = claimed_task

        try:
            self._prepare_task_for_run(task)
            state = self.workflow_engine.run(task.id)
            if state.status == TaskStatus.FAILED:
                err = state.errors[-1] if state.errors else "Workflow failed"
                self._persist_workflow_failure(task_id, RuntimeError(err))
                return RunWorkflowResult(
                    success=False,
                    task_id=task_id,
                    report_id=None,
                    title=None,
                    summary=None,
                    error=err,
                    state=state,
                )
        except Exception as exc:
            logger.exception("Workflow failed: %s", exc)
            err = self._persist_workflow_failure(task_id, exc)
            state = WorkflowState(
                task_id=task_id,
                company_name=task.company_name,
                question=task.question,
                status=TaskStatus.FAILED,
                errors=[err],
            )
            return RunWorkflowResult(
                success=False,
                task_id=task_id,
                report_id=None,
                title=None,
                summary=None,
                error=err,
                state=state,
            )

        report_row = self.artifacts.get_report_by_task_id(task_id)
        report_id = report_row.id if report_row else None
        report_title = report_row.title if report_row else None
        summary_text: str | None = None
        if report_row and report_row.content:
            raw = report_row.content.strip()
            summary_text = raw[:200] + ("..." if len(raw) > 200 else "")

        return RunWorkflowResult(
            success=True,
            task_id=task_id,
            report_id=report_id,
            title=report_title,
            summary=summary_text,
            error=None,
            state=state,
        )

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
        self.artifacts.delete_task_outputs(task.id)
        self.db.commit()
        self.db.refresh(task)

    def _delete_task_outputs(self, task_id: str) -> None:
        self.artifacts.delete_task_outputs(task_id)

    def _persist_workflow_failure(self, task_id: str, exc: Exception) -> str:
        root_msg = str(exc)
        self.db.rollback()
        try:
            task_again = self.get_research_task(task_id)
            if task_again is not None:
                self._delete_task_outputs(task_id)
                task_again.status = TaskStatusORM.FAILED
                task_again.error_message = root_msg
                self.db.add(task_again)
                self.db.commit()
            return root_msg
        except Exception as persist_exc:
            logger.exception("Unable to persist failed task state: %s", persist_exc)
            self.db.rollback()
            return f"{root_msg} | unable to persist failed task state: {persist_exc}"

    def get_report(self, task_id: str) -> ReportRead | None:
        return ReportOutputService(self.db, self.llm_provider).get_report(task_id)

    def get_report_for_output(self, task_id: str) -> ReportRead | None:
        """Read reports through the final output compliance boundary."""
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


class ResearchWorkflowService(WorkflowFacade):
    """Backward-compatible name for existing routes and tests."""
