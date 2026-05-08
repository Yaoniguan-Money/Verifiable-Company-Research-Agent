from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.deps import get_chat_service
from app.api.guards import REPORT_NOT_GENERATED, TASK_NOT_FOUND
from app.schemas.research_api import ChatRequest, ChatResponse
from app.services.chat import ChatService

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat_with_report(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    try:
        out = service.chat_with_task(
            task_id=body.task_id,
            message=body.message,
            background_tasks=background_tasks,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail in {TASK_NOT_FOUND, REPORT_NOT_GENERATED}:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
    return ChatResponse(
        task_id=out.task_id,
        message=out.message,
        answer=out.answer,
        compliance_status=out.compliance_status,
        violations=out.violations,
    )
