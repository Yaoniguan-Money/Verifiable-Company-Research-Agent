"""ExtractedFact —— 由 LLM 从 chunk 中抽取的结构化事实。

为什么 ``value`` 用字符串而不是 Numeric：
- 真实世界的口径千差万别（"亿元" vs "万元"、"FY2023" vs "2023年12月"），
  阶段 1 优先保留原始表述以便 citation 显示；
- 阶段 3 引入归一化时，再追加 ``normalized_value`` / ``unit`` 字段。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.db.models.research_task import ResearchTask
    from app.db.models.source import EvidenceChunk, Source
    from app.db.models.verification import VerificationResult


class ExtractedFact(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "extracted_facts"

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("evidence_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    claim: Mapped[str] = mapped_column(Text, nullable=False)
    metric_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    period: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    task: Mapped[ResearchTask] = relationship(back_populates="extracted_facts")
    source: Mapped[Source] = relationship(back_populates="facts")
    chunk: Mapped[EvidenceChunk] = relationship(back_populates="facts")
    verification: Mapped[VerificationResult | None] = relationship(
        back_populates="fact",
        cascade="all, delete-orphan",
        uselist=False,
    )
