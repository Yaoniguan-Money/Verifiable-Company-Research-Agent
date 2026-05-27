"""阶段 5F：温记忆提取闭环集成测试。"""

from __future__ import annotations

from app.db.init_db import ensure_default_user
from app.db.models import Message, Report, User, UserMemory
from app.db.models import Session as UserSession
from app.schemas.common import ComplianceStatus
from app.schemas.memory import MemoryOperation
from app.services.memory_extraction_coordinator import (
    MIN_NEW_MESSAGES,
    MemoryExtractionCoordinator,
)
from app.services.memory_persistence import MemoryPersistenceService
from app.services.research_workflow import ResearchWorkflowService
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession


def _noop_operation() -> MemoryOperation:
    return MemoryOperation.model_validate(
        {
            "op": "NOOP",
            "reason": "本轮仅寒暄，无长期记忆价值",
        }
    )


def _add_operation() -> MemoryOperation:
    return MemoryOperation.model_validate(
        {
            "op": "ADD",
            "memory_type": "risk_focus",
            "key": "focus",
            "value": "现金流风险",
            "confidence": 0.9,
            "reason": "用户连续追问现金流波动",
        }
    )


def _count_memories(db: OrmSession, *, user_id: str) -> int:
    stmt = select(UserMemory).where(UserMemory.user_id == user_id)
    return len(list(db.scalars(stmt)))


def test_short_messages_should_not_trigger_every_round(db: OrmSession) -> None:
    coordinator = MemoryExtractionCoordinator()
    events: list[tuple[str, int, int]] = []
    session_id = "s_short"

    for latest_count in (1, 2, 3):
        did_trigger = coordinator.maybe_trigger_extraction(
            session_id=session_id,
            latest_message_count=latest_count,
            on_trigger=lambda sid, latest, new: events.append((sid, latest, new)),
        )
        assert not did_trigger

    assert events == []


def test_reach_threshold_should_trigger_background_callback(db: OrmSession) -> None:
    coordinator = MemoryExtractionCoordinator()
    events: list[tuple[str, int, int]] = []

    did_trigger = coordinator.maybe_trigger_extraction(
        session_id="s_threshold",
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=lambda sid, latest, new: events.append((sid, latest, new)),
    )

    assert did_trigger
    assert events == [("s_threshold", MIN_NEW_MESSAGES, MIN_NEW_MESSAGES)]


def test_noop_should_not_write_user_memories(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)

    affected = service.apply_operations(user_id=user.id, operations=[_noop_operation()])

    assert affected == 0
    assert _count_memories(db, user_id=user.id) == 0


def test_add_should_write_user_memories(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)

    affected = service.apply_operations(user_id=user.id, operations=[_add_operation()])

    assert affected == 1
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == user.id)
        .where(UserMemory.memory_type == "risk_focus")
        .where(UserMemory.key == "focus")
        .where(UserMemory.is_active.is_(True))
    )
    memory = db.scalar(stmt)
    assert memory is not None
    assert memory.value == "现金流风险"


def test_running_reentry_should_not_duplicate_trigger_and_should_mark_dirty(db: OrmSession) -> None:
    coordinator = MemoryExtractionCoordinator()
    events: list[str] = []
    reentered = False

    def callback(session_id: str, latest_count: int, _: int) -> None:
        nonlocal reentered
        events.append(f"{session_id}:{latest_count}")
        if reentered:
            return
        reentered = True
        reentry = coordinator.maybe_trigger_extraction(
            session_id=session_id,
            latest_message_count=latest_count + MIN_NEW_MESSAGES,
            on_trigger=lambda *_: events.append("unexpected"),
        )
        assert not reentry

    did_trigger = coordinator.maybe_trigger_extraction(
        session_id="s_running",
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=callback,
    )

    assert did_trigger
    assert events == [
        f"s_running:{MIN_NEW_MESSAGES}",
        f"s_running:{MIN_NEW_MESSAGES * 2}",
    ]
    assert not coordinator.is_dirty("s_running")
    assert not coordinator.is_running("s_running")
    assert coordinator.get_watermark("s_running") == MIN_NEW_MESSAGES * 2


def test_multi_session_should_not_pollute_each_other(db: OrmSession) -> None:
    user = ensure_default_user(db)
    session_a = UserSession(user_id=user.id)
    session_b = UserSession(user_id=user.id)
    db.add(session_a)
    db.add(session_b)
    db.flush()

    coordinator = MemoryExtractionCoordinator()
    events: list[str] = []
    coordinator.maybe_trigger_extraction(
        session_id=session_a.id,
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=lambda sid, *_: events.append(sid),
    )
    coordinator.maybe_trigger_extraction(
        session_id=session_b.id,
        latest_message_count=MIN_NEW_MESSAGES,
        on_trigger=lambda sid, *_: events.append(sid),
    )

    assert set(events) == {session_a.id, session_b.id}
    assert coordinator.get_watermark(session_a.id) == MIN_NEW_MESSAGES
    assert coordinator.get_watermark(session_b.id) == MIN_NEW_MESSAGES


def test_chat_route_should_record_messages_and_trigger_warm_memory(
    client: TestClient,
    db: OrmSession,
) -> None:
    user = User(username="memory_chat_user", email=None)
    db.add(user)
    db.commit()
    db.refresh(user)
    task = ResearchWorkflowService(db).create_research_task(
        company_name="记忆测试公司",
        question="请分析经营风险",
        user_id=user.id,
    )
    db.add(
        Report(
            task_id=task.id,
            title="记忆测试报告",
            content="这是一份用于阶段 5 chat 记忆触发测试的合规报告。",
            citations=[],
            compliance_status=ComplianceStatus.PASSED.value,
        )
    )
    db.commit()

    first = client.post(
        "/api/chat",
        json={"task_id": task.id, "message": "我关注现金流风险"},
    )
    assert first.status_code == 200
    db.refresh(task)
    assert task.session_id is not None
    assert _count_messages(db, session_id=task.session_id) == 2
    assert _active_memory(db, user_id=task.user_id, key="focus") is None

    second = client.post(
        "/api/chat",
        json={"task_id": task.id, "message": "继续帮我关注现金流风险"},
    )
    assert second.status_code == 200
    assert _count_messages(db, session_id=task.session_id) == 4

    memory = _active_memory(db, user_id=task.user_id, key="focus")
    assert memory is not None
    assert memory.memory_type == "risk_focus"
    assert memory.value == "现金流风险"


def _count_messages(db: OrmSession, *, session_id: str) -> int:
    stmt = select(Message).where(Message.session_id == session_id)
    return len(list(db.scalars(stmt)))


def _active_memory(db: OrmSession, *, user_id: str, key: str) -> UserMemory | None:
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == user_id)
        .where(UserMemory.key == key)
        .where(UserMemory.is_active.is_(True))
    )
    return db.scalar(stmt)
