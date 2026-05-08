"""MemoryOperation persistence service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import UserMemory
from app.schemas.memory import MemoryOperation, MemoryOperationType


class MemoryPersistenceService:
    """将 MemoryOperation 应用到 user_memories 的最小服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def apply_operations(self, *, user_id: str, operations: list[MemoryOperation]) -> int:
        affected = 0
        for operation in operations:
            if self.apply_operation(user_id=user_id, operation=operation):
                affected += 1
        # 由调用方决定 commit 时机；这里仅 flush 以便当前事务内可见。
        self.db.flush()
        return affected

    def apply_operation(self, *, user_id: str, operation: MemoryOperation) -> bool:
        op = operation.op
        if op == MemoryOperationType.NOOP:
            return False
        if op == MemoryOperationType.ADD:
            return self._apply_add(user_id=user_id, operation=operation)
        if op == MemoryOperationType.UPDATE:
            return self._apply_update(user_id=user_id, operation=operation)
        if op == MemoryOperationType.DELETE:
            return self._apply_delete(user_id=user_id, operation=operation)
        return False

    def _find_active_memory(
        self,
        *,
        user_id: str,
        memory_layer: str,
        memory_type: str,
        key: str,
    ) -> UserMemory | None:
        # Session 配置为 autoflush=False，这里手动 flush 以确保同事务内新增记录可被查询到。
        self.db.flush()
        stmt = (
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .where(UserMemory.memory_layer == memory_layer)
            .where(UserMemory.memory_type == memory_type)
            .where(UserMemory.key == key)
            .where(UserMemory.is_active.is_(True))
            .order_by(UserMemory.created_at.desc())
        )
        return self.db.scalar(stmt)

    def _apply_add(self, *, user_id: str, operation: MemoryOperation) -> bool:
        # MVP 策略：若 active 记录已存在，则做更新以避免重复记录。
        existing = self._find_active_memory(
            user_id=user_id,
            memory_layer=operation.memory_layer.value,
            memory_type=operation.memory_type or "",
            key=operation.key or "",
        )
        if existing is None:
            self.db.add(
                UserMemory(
                    user_id=user_id,
                    memory_layer=operation.memory_layer.value,
                    memory_type=operation.memory_type or "",
                    key=operation.key or "",
                    value=operation.value or "",
                    confidence=operation.confidence,
                    reason=operation.reason or "",
                    is_active=True,
                )
            )
            return True

        existing.value = operation.value or ""
        existing.confidence = operation.confidence
        existing.reason = operation.reason or existing.reason
        existing.is_active = True
        return True

    def _apply_update(self, *, user_id: str, operation: MemoryOperation) -> bool:
        # MVP 策略：找不到时自动创建，避免上游 pipeline 断裂。
        existing = self._find_active_memory(
            user_id=user_id,
            memory_layer=operation.memory_layer.value,
            memory_type=operation.memory_type or "",
            key=operation.key or "",
        )
        if existing is None:
            self.db.add(
                UserMemory(
                    user_id=user_id,
                    memory_layer=operation.memory_layer.value,
                    memory_type=operation.memory_type or "",
                    key=operation.key or "",
                    value=operation.value or "",
                    confidence=operation.confidence,
                    reason=operation.reason or "",
                    is_active=True,
                )
            )
            return True

        existing.value = operation.value or existing.value
        existing.confidence = operation.confidence
        existing.reason = operation.reason or existing.reason
        existing.is_active = True
        return True

    def _apply_delete(self, *, user_id: str, operation: MemoryOperation) -> bool:
        existing = self._find_active_memory(
            user_id=user_id,
            memory_layer=operation.memory_layer.value,
            memory_type=operation.memory_type or "",
            key=operation.key or "",
        )
        if existing is None:
            # 安全跳过：DELETE 目标不存在时不报错。
            return False

        existing.is_active = False
        existing.reason = operation.reason or existing.reason
        if operation.confidence is not None:
            existing.confidence = operation.confidence
        return True
