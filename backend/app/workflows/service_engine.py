"""Legacy 顺序执行工作流引擎。

默认使用 LangGraph；本引擎保留是为了：
- 老脚本/回归仍在用 ``WORKFLOW_ENGINE=service``；
- 排查问题时可以切回逐步执行确认业务行为是否与图编排一致。

业务逻辑全部委托给 ``WorkflowStepExecutor``（再下沉到 ``ResearchDomainServices``），
本类只负责包一层 ``WorkflowState`` 生命周期。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.providers.llm import LLMProvider
from app.providers.search import SearchProvider
from app.repositories import ResearchArtifactRepository, ResearchTaskRepository
from app.schemas.common import TaskStatus
from app.schemas.workflow import WorkflowState
from app.services.workflow_audit import WorkflowAuditService
from app.services.workflow_step_executor import WorkflowStepExecutor


class ServiceWorkflowEngine:
    """逐步执行版工作流引擎，与 LangGraph 引擎行为对齐。"""

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
        self.tasks = ResearchTaskRepository(db)
        self.step_executor = WorkflowStepExecutor(
            db=db,
            settings=settings,
            artifacts=artifacts,
            search_provider=search_provider,
            llm_provider=llm_provider,
            audit=audit,
        )

    def run(self, task_id: str) -> WorkflowState:
        task = self.tasks.get(task_id)
        if task is None:
            raise ValueError("Task does not exist")

        state = WorkflowState(
            task_id=task.id,
            company_name=task.company_name,
            question=task.question,
            status=TaskStatus.RUNNING,
        )
        self.step_executor.run_service_workflow_steps(task, state)
        state.status = TaskStatus.COMPLETED
        return state

    def get_status(self, task_id: str) -> WorkflowState | None:
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

    def resume(self, task_id: str) -> WorkflowState:
        return self.run(task_id)
