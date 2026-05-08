"""阶段 5E：user_memories 持久化测试。"""

from __future__ import annotations

from app.db.init_db import ensure_default_user
from app.db.models import User, UserMemory
from app.schemas.memory import MemoryOperation
from app.services.memory_persistence import MemoryPersistenceService
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession


def _op(payload: dict) -> MemoryOperation:
    return MemoryOperation.model_validate(payload)


def _list_memories(db: OrmSession, *, user_id: str) -> list[UserMemory]:
    stmt = (
        select(UserMemory)
        .where(UserMemory.user_id == user_id)
        .order_by(UserMemory.created_at, UserMemory.id)
    )
    return list(db.scalars(stmt))


def test_add_should_insert_active_memory(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)

    affected = service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_type": "user_preference",
                    "key": "report_style",
                    "value": "简洁",
                    "confidence": 0.8,
                    "reason": "用户明确偏好简洁表达",
                }
            )
        ],
    )

    memories = _list_memories(db, user_id=user.id)
    assert affected == 1
    assert len(memories) == 1
    assert memories[0].is_active
    assert memories[0].memory_type == "user_preference"
    assert memories[0].key == "report_style"


def test_update_should_modify_existing_memory(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)
    service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_type": "risk_focus",
                    "key": "focus",
                    "value": "供应链风险",
                    "confidence": 0.4,
                    "reason": "初始偏好",
                }
            )
        ],
    )

    service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "UPDATE",
                    "memory_type": "risk_focus",
                    "key": "focus",
                    "value": "现金流风险",
                    "confidence": 0.9,
                    "reason": "用户修正关注点",
                }
            )
        ],
    )

    memories = _list_memories(db, user_id=user.id)
    assert len(memories) == 1
    assert memories[0].value == "现金流风险"
    assert memories[0].confidence == 0.9
    assert memories[0].reason == "用户修正关注点"


def test_update_missing_target_should_create(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)

    affected = service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "UPDATE",
                    "memory_type": "recent_company",
                    "key": "company",
                    "value": "测试科技",
                    "confidence": 0.7,
                    "reason": "MVP 策略：不存在则创建",
                }
            )
        ],
    )

    memories = _list_memories(db, user_id=user.id)
    assert affected == 1
    assert len(memories) == 1
    assert memories[0].is_active
    assert memories[0].memory_type == "recent_company"


def test_delete_should_soft_deactivate(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)
    service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_type": "interested_industry",
                    "key": "industry",
                    "value": "半导体",
                    "confidence": 0.6,
                    "reason": "用户反复提及",
                }
            )
        ],
    )

    affected = service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "DELETE",
                    "memory_type": "interested_industry",
                    "key": "industry",
                    "reason": "用户表示不再关注",
                }
            )
        ],
    )

    memories = _list_memories(db, user_id=user.id)
    assert affected == 1
    assert len(memories) == 1
    assert not memories[0].is_active
    assert memories[0].reason == "用户表示不再关注"


def test_delete_missing_target_should_not_crash(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)

    affected = service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "DELETE",
                    "memory_type": "risk_focus",
                    "key": "focus",
                    "reason": "不存在也应安全跳过",
                }
            )
        ],
    )

    memories = _list_memories(db, user_id=user.id)
    assert affected == 0
    assert memories == []


def test_noop_should_not_write_memory(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)

    affected = service.apply_operations(
        user_id=user.id,
        operations=[_op({"op": "NOOP", "reason": "无长期记忆价值"})],
    )

    memories = _list_memories(db, user_id=user.id)
    assert affected == 0
    assert memories == []


def test_apply_multiple_operations_batch(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)

    affected = service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_type": "user_preference",
                    "key": "report_style",
                    "value": "简洁",
                    "confidence": 0.8,
                    "reason": "初始偏好",
                }
            ),
            _op(
                {
                    "op": "UPDATE",
                    "memory_type": "user_preference",
                    "key": "report_style",
                    "value": "详细",
                    "confidence": 0.95,
                    "reason": "用户要求更详细",
                }
            ),
            _op(
                {
                    "op": "NOOP",
                    "reason": "寒暄",
                }
            ),
        ],
    )

    memories = _list_memories(db, user_id=user.id)
    assert affected == 2
    assert len(memories) == 1
    assert memories[0].value == "详细"


def test_different_users_should_not_pollute_each_other(db: OrmSession) -> None:
    user1 = ensure_default_user(db)
    user2 = db.scalar(select(User).where(User.username == "user_2"))
    if user2 is None:
        user2 = User(username="user_2", email=None)
        db.add(user2)
        db.commit()
        db.refresh(user2)

    service = MemoryPersistenceService(db)
    service.apply_operations(
        user_id=user1.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_type": "risk_focus",
                    "key": "focus",
                    "value": "合规风险",
                    "confidence": 0.6,
                    "reason": "user1 偏好",
                }
            )
        ],
    )
    service.apply_operations(
        user_id=user2.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_type": "risk_focus",
                    "key": "focus",
                    "value": "现金流风险",
                    "confidence": 0.7,
                    "reason": "user2 偏好",
                }
            )
        ],
    )

    m1 = _list_memories(db, user_id=user1.id)
    m2 = _list_memories(db, user_id=user2.id)
    assert len(m1) == 1 and len(m2) == 1
    assert m1[0].value == "合规风险"
    assert m2[0].value == "现金流风险"


def test_memory_type_and_key_locator_should_be_precise(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)
    service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_type": "risk_focus",
                    "key": "focus_a",
                    "value": "供应链",
                    "confidence": 0.5,
                    "reason": "A",
                }
            ),
            _op(
                {
                    "op": "ADD",
                    "memory_type": "risk_focus",
                    "key": "focus_b",
                    "value": "现金流",
                    "confidence": 0.6,
                    "reason": "B",
                }
            ),
            _op(
                {
                    "op": "UPDATE",
                    "memory_type": "risk_focus",
                    "key": "focus_b",
                    "value": "财务造假风险",
                    "confidence": 0.88,
                    "reason": "仅更新 B",
                }
            ),
        ],
    )

    memories = _list_memories(db, user_id=user.id)
    by_key = {m.key: m for m in memories}
    assert by_key["focus_a"].value == "供应链"
    assert by_key["focus_b"].value == "财务造假风险"
    assert by_key["focus_b"].confidence == 0.88
    assert by_key["focus_b"].reason == "仅更新 B"


def test_confidence_and_reason_should_be_saved_and_updated(db: OrmSession) -> None:
    user = ensure_default_user(db)
    service = MemoryPersistenceService(db)
    service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "ADD",
                    "memory_type": "recent_company",
                    "key": "company",
                    "value": "A 公司",
                    "confidence": 0.3,
                    "reason": "首次提及",
                }
            )
        ],
    )
    service.apply_operations(
        user_id=user.id,
        operations=[
            _op(
                {
                    "op": "UPDATE",
                    "memory_type": "recent_company",
                    "key": "company",
                    "value": "A 公司",
                    "confidence": 0.92,
                    "reason": "用户连续三轮确认",
                }
            )
        ],
    )

    memories = _list_memories(db, user_id=user.id)
    assert len(memories) == 1
    assert memories[0].confidence == 0.92
    assert memories[0].reason == "用户连续三轮确认"
