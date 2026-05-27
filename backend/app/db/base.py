"""SQLAlchemy 2.0 Declarative Base 与通用 Mixin。

设计要点：
1. 主键统一为 ``String(36)`` UUID 字符串，跨 SQLite / PostgreSQL 兼容，
   不依赖 autoincrement，分布式友好。
2. 时间戳统一 ``DateTime(timezone=True) + server_default=func.now()``，
   时区安全，落库时间不依赖应用层。
3. JSON 字段统一用 ``JSON`` 类型（SQLAlchemy 会按方言映射，SQLite 与 PG 都可用）。

Mixin 仅提供"通用列"，不掺杂业务字段，避免后续模型臃肿。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """所有 ORM 模型的统一基类。"""


class UUIDPKMixin:
    """统一的 UUID 主键。"""

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=_new_uuid,
    )


class TimestampMixin:
    """统一的创建/更新时间戳。

    - ``created_at``：插入时由数据库赋值。
    - ``updated_at``：插入与更新时由数据库赋值（通过 ``onupdate``）。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CreatedAtMixin:
    """只关心 created_at（适合 messages / facts / verifications 等只追加表）。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
