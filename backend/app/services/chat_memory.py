"""Chat-message persistence and lightweight memory extraction trigger."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from app.db import session as db_session
from app.db.models import Message, MessageRole, ResearchTask
from app.db.models import Session as UserSession
from app.schemas.memory import MemoryOperation, MemoryOperationType
from app.services.memory_extraction_coordinator import MemoryExtractionCoordinator
from app.services.memory_persistence import MemoryPersistenceService

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_COORDINATOR = MemoryExtractionCoordinator()


class ChatMemoryService:
    """把 chat 消息写入会话，并按阈值触发温记忆提取。"""

    def __init__(
        self,
        db: OrmSession,
        coordinator: MemoryExtractionCoordinator | None = None,
    ) -> None:
        self.db = db
        self.coordinator = coordinator or DEFAULT_MEMORY_COORDINATOR

    def record_turn_for_task(
        self,
        *,
        task: ResearchTask,
        user_message: str,
        assistant_answer: str,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        session_id = self._ensure_task_session(task)
        self.db.add_all(
            [
                Message(
                    session_id=session_id,
                    role=MessageRole.USER.value,
                    content=user_message,
                ),
                Message(
                    session_id=session_id,
                    role=MessageRole.ASSISTANT.value,
                    content=assistant_answer,
                ),
            ]
        )
        self.db.commit()
        latest_message_count = self._count_messages(session_id=session_id)

        if not self.coordinator.should_extract(
            session_id=session_id,
            latest_message_count=latest_message_count,
        ):
            return

        if background_tasks is not None:
            background_tasks.add_task(
                run_memory_extraction_for_session,
                session_id,
                task.user_id,
                latest_message_count,
            )
            return

        self._run_extraction_for_session(
            session_id=session_id,
            user_id=task.user_id,
            latest_message_count=latest_message_count,
        )

    def _ensure_task_session(self, task: ResearchTask) -> str:
        if task.session_id is not None:
            existing = self.db.get(UserSession, task.session_id)
            if existing is not None:
                return existing.id

        session = UserSession(user_id=task.user_id)
        self.db.add(session)
        self.db.flush()
        task.session_id = session.id
        self.db.add(task)
        self.db.flush()
        return session.id

    def _count_messages(self, *, session_id: str) -> int:
        stmt = select(func.count()).select_from(Message).where(Message.session_id == session_id)
        return int(self.db.scalar(stmt) or 0)

    def _run_extraction_for_session(
        self,
        *,
        session_id: str,
        user_id: str,
        latest_message_count: int,
    ) -> bool:
        def on_trigger(trigger_session_id: str, latest_count: int, new_messages: int) -> None:
            operations = self._extract_operations(
                session_id=trigger_session_id,
                latest_message_count=latest_count,
                new_messages=new_messages,
            )
            MemoryPersistenceService(self.db).apply_operations(
                user_id=user_id,
                operations=operations,
            )
            self.db.commit()

        return self.coordinator.maybe_trigger_extraction(
            session_id=session_id,
            latest_message_count=latest_message_count,
            on_trigger=on_trigger,
        )

    def _extract_operations(
        self,
        *,
        session_id: str,
        latest_message_count: int,
        new_messages: int,
    ) -> list[MemoryOperation]:
        messages = self._list_recent_messages(
            session_id=session_id,
            latest_message_count=latest_message_count,
            new_messages=new_messages,
        )
        user_text = "\n".join(
            message.content for message in messages if message.role == MessageRole.USER.value
        )

        if "现金流" in user_text:
            return [
                MemoryOperation(
                    op=MemoryOperationType.ADD,
                    memory_type="risk_focus",
                    key="focus",
                    value="现金流风险",
                    confidence=0.8,
                    reason="用户在温记忆触发窗口内提及现金流关注点",
                )
            ]
        if "简洁" in user_text:
            return [
                MemoryOperation(
                    op=MemoryOperationType.ADD,
                    memory_type="user_preference",
                    key="report_style",
                    value="简洁",
                    confidence=0.8,
                    reason="用户在温记忆触发窗口内表达简洁偏好",
                )
            ]

        return [
            MemoryOperation(
                op=MemoryOperationType.NOOP,
                reason="本轮消息没有可稳定保存的长期偏好或关注点",
            )
        ]

    def _list_recent_messages(
        self,
        *,
        session_id: str,
        latest_message_count: int,
        new_messages: int,
    ) -> list[Message]:
        offset = max(latest_message_count - new_messages, 0)
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at, Message.id)
            .offset(offset)
            .limit(new_messages)
        )
        return list(self.db.scalars(stmt))


def run_memory_extraction_for_session(
    session_id: str,
    user_id: str,
    latest_message_count: int,
) -> None:
    """FastAPI BackgroundTasks 入口，使用独立 DB session 避免请求 session 生命周期问题。"""
    with db_session.SessionLocal() as db:
        try:
            ChatMemoryService(db)._run_extraction_for_session(
                session_id=session_id,
                user_id=user_id,
                latest_message_count=latest_message_count,
            )
        except Exception:
            db.rollback()
            logger.exception("Warm memory extraction failed for session_id=%s", session_id)
            raise
