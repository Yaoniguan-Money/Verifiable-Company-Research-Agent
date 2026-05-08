"""来源 API（阶段 1.D）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_research_workflow_service
from app.api.guards import require_task
from app.schemas.research_api import SourceListResponse
from app.schemas.source import SourceRead
from app.services.research_workflow import ResearchWorkflowService

router = APIRouter(prefix="/api", tags=["sources"])


@router.get("/sources/{task_id}", response_model=SourceListResponse)
def list_sources_for_task(
    task_id: str,
    service: ResearchWorkflowService = Depends(get_research_workflow_service),
) -> SourceListResponse:
    require_task(service, task_id)
    rows = service.list_sources(task_id)
    items = [
        SourceRead(
            id=r.id,
            task_id=r.task_id,
            title=r.title,
            url=r.url,
            source_type=r.source_type,
            published_at=r.published_at,
            retrieved_at=r.retrieved_at,
            raw_content=r.raw_content,
            credibility_score=r.credibility_score,
            source_metadata=r.source_metadata,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return SourceListResponse(task_id=task_id, items=items)
