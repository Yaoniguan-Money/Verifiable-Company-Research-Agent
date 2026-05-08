"""API 层依赖。"""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.providers.factory import ProviderFactory
from app.services.chat import ChatService
from app.services.research_workflow import ResearchWorkflowService


def get_research_workflow_service(
    db: Session = Depends(get_db),
) -> ResearchWorkflowService:
    """为路由注入 `ResearchWorkflowService`。"""
    providers = ProviderFactory()
    return ResearchWorkflowService(
        db,
        search_provider=providers.create_search_provider(),
        llm_provider=providers.create_llm_provider(),
    )


def get_chat_service(
    db: Session = Depends(get_db),
) -> ChatService:
    providers = ProviderFactory()
    return ChatService(db, llm_provider=providers.create_llm_provider())
