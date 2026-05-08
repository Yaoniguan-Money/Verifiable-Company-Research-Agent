"""Report —— 研究任务的最终交付物。

阶段 1：
- ``content`` 用 Markdown 文本承载；
- ``citations`` 以 JSON 数组保存，每项形如：
    {"chunk_id": "...", "source_id": "...", "url": "...", "title": "...",
     "retrieved_at": "..."}
- ``compliance_status``：阶段 1 默认 "passed"，阶段 4 起由 ComplianceCheck 节点写入。
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.db.models.research_task import ResearchTask


class ComplianceStatus(str, Enum):
    PASSED = "passed"        # 通过合规检查
    REWRITTEN = "rewritten"  # 检测到违规并已改写
    BLOCKED = "blocked"      # 命中红线被拦截
    SKIPPED = "skipped"      # 阶段 1 默认（合规模块尚未实装时）


class Report(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "reports"

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    compliance_status: Mapped[ComplianceStatus] = mapped_column(
        String(16),
        nullable=False,
        default=ComplianceStatus.SKIPPED,
    )

    task: Mapped[ResearchTask] = relationship(back_populates="report")
