"""Read-side memory context assembly for hot / warm / cold layers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Message, UserMemory


@dataclass(frozen=True, slots=True)
class MemoryContext:
    hot_messages: list[str]
    warm_memories: list[UserMemory]
    cold_memories: list[UserMemory]

    @property
    def has_persistent_memory(self) -> bool:
        return bool(self.warm_memories or self.cold_memories)


class MemoryContextService:
    """Assemble memory by layer without deciding how an LLM should use it."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def build_context(
        self,
        *,
        user_id: str,
        session_id: str | None = None,
        hot_message_limit: int = 6,
        persistent_limit: int = 20,
    ) -> MemoryContext:
        return MemoryContext(
            hot_messages=self._list_hot_messages(
                session_id=session_id,
                limit=hot_message_limit,
            ),
            warm_memories=self._list_active_memories(
                user_id=user_id,
                layer="warm",
                limit=persistent_limit,
            ),
            cold_memories=self._list_active_memories(
                user_id=user_id,
                layer="cold",
                limit=persistent_limit,
            ),
        )

    def _list_hot_messages(self, *, session_id: str | None, limit: int) -> list[str]:
        if session_id is None or limit <= 0:
            return []
        stmt = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )
        rows = list(self.db.scalars(stmt))
        rows.reverse()
        return [f"{item.role}: {item.content}" for item in rows]

    def _list_active_memories(self, *, user_id: str, layer: str, limit: int) -> list[UserMemory]:
        if limit <= 0:
            return []
        stmt = (
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .where(UserMemory.memory_layer == layer)
            .where(UserMemory.is_active.is_(True))
            .order_by(UserMemory.updated_at.desc(), UserMemory.created_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))
