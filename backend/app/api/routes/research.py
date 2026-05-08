from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_research_workflow_service
from app.api.guards import REPORT_NOT_GENERATED, require_task
from app.db.models import ResearchTask
from app.schemas.common import TaskStatus
from app.schemas.research_api import (
    CreateResearchTaskRequest,
    CreateResearchTaskResponse,
    ReportResponse,
    ResearchTaskDetailResponse,
    RunResearchTaskResponse,
)
from app.services.research_workflow import ResearchWorkflowService, RunWorkflowResult

router = APIRouter(prefix="/api/research", tags=["research"])


def _task_status_str(task: ResearchTask) -> str:
    st = task.status
    if isinstance(st, str):
        return st
    return getattr(st, "value", str(st))


def _task_to_detail(task: ResearchTask) -> ResearchTaskDetailResponse:
    return ResearchTaskDetailResponse(
        task_id=task.id,
        company_name=task.company_name,
        question=task.question,
        status=_task_status_str(task),
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.post("/tasks", response_model=CreateResearchTaskResponse, status_code=status.HTTP_201_CREATED)
def create_research_task(
    body: CreateResearchTaskRequest,
    service: ResearchWorkflowService = Depends(get_research_workflow_service),
) -> CreateResearchTaskResponse:
    try:
        task = service.create_research_task(
            company_name=body.company_name,
            question=body.question,
            session_id=body.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CreateResearchTaskResponse(task_id=task.id, status=TaskStatus.CREATED)


@router.get("/tasks/{task_id}", response_model=ResearchTaskDetailResponse)
def get_research_task(
    task_id: str,
    service: ResearchWorkflowService = Depends(get_research_workflow_service),
) -> ResearchTaskDetailResponse:
    task = require_task(service, task_id)
    return _task_to_detail(task)


@router.post("/tasks/{task_id}/run", response_model=RunResearchTaskResponse)
def run_research_task(
    task_id: str,
    service: ResearchWorkflowService = Depends(get_research_workflow_service),
) -> RunResearchTaskResponse:
    require_task(service, task_id)

    try:
        outcome: RunWorkflowResult = service.run_workflow(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not outcome.success and not outcome.state.steps and outcome.error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=outcome.error)

    task = service.get_research_task(task_id)
    task_state = _task_status_str(task) if task else "unknown"
    return RunResearchTaskResponse(
        task_id=task_id,
        report_id=outcome.report_id,
        status=task_state,
        title=outcome.title,
        summary=outcome.summary,
        error=outcome.error,
    )


@router.get("/tasks/{task_id}/report", response_model=ReportResponse)
def get_research_task_report(
    task_id: str,
    service: ResearchWorkflowService = Depends(get_research_workflow_service),
) -> ReportResponse:
    require_task(service, task_id)
    rep = service.get_report_for_output(task_id)
    if rep is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=REPORT_NOT_GENERATED)
    return ReportResponse(
        task_id=rep.task_id,
        content=rep.content,
        citations=rep.citations,
        compliance_status=rep.compliance_status,
        title=rep.title,
    )


