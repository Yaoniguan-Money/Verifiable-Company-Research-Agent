from __future__ import annotations

from fastapi import HTTPException, status

from app.db.models import ResearchTask
from app.services.research_workflow import ResearchWorkflowService

TASK_NOT_FOUND = "task not found"
REPORT_NOT_GENERATED = "report not generated"


def require_task(
    service: ResearchWorkflowService,
    task_id: str,
) -> ResearchTask:
    task = service.get_research_task(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=TASK_NOT_FOUND)
    return task
