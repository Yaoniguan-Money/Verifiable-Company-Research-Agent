"""Workflow state and step-result schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.schemas.chunk import Citation
from app.schemas.common import SchemaBase, TaskStatus


class WorkflowStepResult(SchemaBase):
    step_name: str
    success: bool
    message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    output_summary: dict = Field(default_factory=dict)


class WorkflowDecision(SchemaBase):
    """Workflow 条件分支或降级决策。

    只记录工程审计信息，不代表业务事实本身。
    """

    node: str
    reason: str
    message: str
    task_id: str | None = None
    status_counts: dict[str, int] = Field(default_factory=dict)


class WorkflowState(SchemaBase):
    task_id: str
    company_name: str
    question: str
    status: TaskStatus
    current_step: str | None = None
    steps: list[WorkflowStepResult] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    workflow_decisions: list[WorkflowDecision] = Field(default_factory=list)
    intermediate_outputs: dict = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
