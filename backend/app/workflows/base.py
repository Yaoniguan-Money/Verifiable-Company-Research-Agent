from __future__ import annotations

from typing import Protocol

from app.schemas.workflow import WorkflowState


class WorkflowEngine(Protocol):
    """Contract used by the application service to run a research workflow."""

    def run(self, task_id: str) -> WorkflowState:
        raise NotImplementedError

    def get_status(self, task_id: str) -> WorkflowState | None:
        raise NotImplementedError

    def resume(self, task_id: str) -> WorkflowState:
        raise NotImplementedError
