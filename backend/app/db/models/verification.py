"""VerificationResult —— 对单条 fact 的审计结论。

阶段 1 的 Mock 实现会按规则给出 verified / insufficient；
阶段 3 升级为真正的多源交叉验证。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.db.models.fact import ExtractedFact
    from app.db.models.research_task import ResearchTask


class VerificationStatus(str, Enum):
    VERIFIED = "verified"          # 多源一致，可信度较高
    CONFLICTED = "conflicted"      # 来源冲突
    INSUFFICIENT = "insufficient"  # 证据不足
    OUTDATED = "outdated"          # 来源过旧
    REJECTED = "rejected"          # 明显错误或不可信


class VerificationResult(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "verification_results"

    fact_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("extracted_facts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[VerificationStatus] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # JSON list[str]，存 source_id；阶段 3 视需要可改为关联表
    supporting_sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    conflicting_sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    fact: Mapped[ExtractedFact] = relationship(back_populates="verification")
    task: Mapped[ResearchTask] = relationship(back_populates="verification_results")
