"""User / Session / Message 三张表。

阶段 1 仅做最小占位：
- 启动时引导 default_user，API 层默认绑定。
- 不做完整登录注册（后续阶段视需要补齐）。
- Session 与 Message 用于支撑后续追问 / 温记忆，本阶段先建表不强制使用。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.db.models.research_task import ResearchTask
    from app.db.models.user_memory import UserMemory


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class User(UUIDPKMixin, Base):
    """最小占位用户表。"""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at = TimestampMixin.created_at
    updated_at = TimestampMixin.updated_at

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    research_tasks: Mapped[list[ResearchTask]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    memories: Mapped[list[UserMemory]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} username={self.username!r}>"


class Session(UUIDPKMixin, TimestampMixin, Base):
    """会话表（用于支撑追问与温记忆）。"""

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
    research_tasks: Mapped[list[ResearchTask]] = relationship(
        back_populates="session",
    )


class Message(UUIDPKMixin, CreatedAtMixin, Base):
    """会话消息（阶段 1 不强制使用，阶段 5 / 阶段 6 追问时启用）。"""

    __tablename__ = "messages"

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    session: Mapped[Session] = relationship(back_populates="messages")
