"""验证结果 API（阶段 1.D）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_research_workflow_service
from app.api.guards import require_task
from app.schemas.research_api import VerificationListResponse
from app.schemas.verification import VerificationResultRead
from app.services.research_workflow import ResearchWorkflowService

router = APIRouter(prefix="/api", tags=["verification"])


@router.get("/verification/{task_id}", response_model=VerificationListResponse)
def list_verification_for_task(
    task_id: str,
    service: ResearchWorkflowService = Depends(get_research_workflow_service),
) -> VerificationListResponse:
    require_task(service, task_id)
    rows = service.list_verification_results(task_id)
    items = [VerificationResultRead.model_validate(r) for r in rows]
    return VerificationListResponse(task_id=task_id, items=items)
