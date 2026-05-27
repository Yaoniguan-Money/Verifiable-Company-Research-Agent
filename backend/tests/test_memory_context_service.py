from __future__ import annotations

from datetime import datetime, timezone

from app.db.init_db import ensure_default_user
from app.db.models import Message, MessageRole, Session
from app.schemas.memory import MemoryOperation
from app.services.memory_context import MemoryContextService
from app.services.memory_persistence import MemoryPersistenceService
from sqlalchemy.orm import Session as OrmSession


def _op(payload: dict) -> MemoryOperation:
    return MemoryOperation.model_validate(payload)


def test_memory_context_separates_hot_warm_cold_layers(db: OrmSession) -> None:
    user = ensure_default_user(db)
    session = Session(user_id=user.id)
    db.add(session)
    db.flush()
    db.add_all(
        [
            Message(
                session_id=session.id,
                role=MessageRole.USER.value,
                content="first",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ]
    )
    db.flush()
    db.add_all(
        [
            Message(
                session_id=session.id,
                role=MessageRole.ASSISTANT.value,
                content="second",
                created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            )
        ]
    )
    MemoryPersistenceService(db).apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_layer": "warm",
                    "memory_type": "user_preference",
                    "key": "report_style",
                    "value": "concise",
                    "reason": "user preference",
                }
            ),
            _op(
                {
                    "op": "ADD",
                    "memory_layer": "cold",
                    "memory_type": "company_profile",
                    "key": "Sample Public Co",
                    "value": "public company knowledge",
                    "reason": "reusable company context",
                }
            ),
        ],
    )
    db.flush()

    context = MemoryContextService(db).build_context(user_id=user.id, session_id=session.id)

    assert context.hot_messages == ["user: first", "assistant: second"]
    assert [item.key for item in context.warm_memories] == ["report_style"]
    assert [item.key for item in context.cold_memories] == ["Sample Public Co"]
    assert context.has_persistent_memory


def test_memory_persistence_same_key_different_layers_do_not_overwrite(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)
    service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_layer": "warm",
                    "memory_type": "risk_focus",
                    "key": "focus",
                    "value": "cash flow",
                    "reason": "warm preference",
                }
            ),
            _op(
                {
                    "op": "ADD",
                    "memory_layer": "cold",
                    "memory_type": "risk_focus",
                    "key": "focus",
                    "value": "industry cycle",
                    "reason": "cold reusable context",
                }
            ),
        ],
    )
    db.flush()

    context = MemoryContextService(db).build_context(user_id=user.id)

    assert [item.value for item in context.warm_memories] == ["cash flow"]
    assert [item.value for item in context.cold_memories] == ["industry cycle"]
