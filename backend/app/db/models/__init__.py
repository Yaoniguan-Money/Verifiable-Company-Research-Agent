"""集中导出所有 ORM 模型。

在 ``init_db()`` 之前 import 本模块即可保证 SQLAlchemy 能解析所有 relationships。
"""

from app.db.models.fact import ExtractedFact
from app.db.models.report import ComplianceStatus, Report
from app.db.models.research_task import ResearchTask, TaskStatus
from app.db.models.source import EvidenceChunk, Source, SourceType
from app.db.models.user import Message, MessageRole, Session, User
from app.db.models.user_memory import UserMemory
from app.db.models.verification import VerificationResult, VerificationStatus

__all__ = [
    "User",
    "Session",
    "Message",
    "MessageRole",
    "UserMemory",
    "ResearchTask",
    "TaskStatus",
    "Source",
    "SourceType",
    "EvidenceChunk",
    "ExtractedFact",
    "VerificationResult",
    "VerificationStatus",
    "Report",
    "ComplianceStatus",
]
