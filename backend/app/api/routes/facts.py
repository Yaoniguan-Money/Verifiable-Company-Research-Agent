"""抽取事实 API（阶段 1.D）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_research_workflow_service
from app.api.guards import require_task
from app.schemas.fact import ExtractedFactRead
from app.schemas.research_api import FactListResponse
from app.services.research_workflow import ResearchWorkflowService

router = APIRouter(prefix="/api", tags=["facts"])


@router.get("/facts/{task_id}", response_model=FactListResponse)
def list_facts_for_task(
    task_id: str,
    service: ResearchWorkflowService = Depends(get_research_workflow_service),
) -> FactListResponse:
    require_task(service, task_id)
    rows = service.list_extracted_facts(task_id)
    items = [ExtractedFactRead.model_validate(r) for r in rows]
    return FactListResponse(task_id=task_id, items=items)
