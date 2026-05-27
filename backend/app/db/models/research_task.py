"""研究任务表 —— workflow 的根节点。

一个 ResearchTask 在生命周期内串起：
    sources → evidence_chunks → extracted_facts → verification_results → report
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.db.models.fact import ExtractedFact
    from app.db.models.report import Report
    from app.db.models.source import EvidenceChunk, Source
    from app.db.models.user import Session, User
    from app.db.models.verification import VerificationResult


class TaskStatus(str, Enum):
    """workflow 状态机。

    状态流转（阶段 1）：
        CREATED → RUNNING → COMPLETED
                         ↘ FAILED
    """

    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ResearchTask(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "research_tasks"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        String(16),
        nullable=False,
        default=TaskStatus.CREATED,
    )
    # 失败时记录最后一次错误，便于追踪
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="research_tasks")
    session: Mapped[Session | None] = relationship(back_populates="research_tasks")

    sources: Mapped[list[Source]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    evidence_chunks: Mapped[list[EvidenceChunk]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    extracted_facts: Mapped[list[ExtractedFact]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    verification_results: Mapped[list[VerificationResult]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )
    report: Mapped[Report | None] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        uselist=False,
    )
