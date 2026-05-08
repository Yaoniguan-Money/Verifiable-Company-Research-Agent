"""LLM Provider 抽象接口（仅局部能力，不控制工作流）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.schemas.chunk import Citation, EvidenceChunkRead
from app.schemas.common import ComplianceStatus, SchemaBase
from app.schemas.fact import ExtractedFactCreate, ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from pydantic import Field


class ComplianceCheckResult(SchemaBase):
    is_compliant: bool
    status: ComplianceStatus
    violations: list[str] = Field(default_factory=list)
    rewritten_text: str | None = None
    checked_at: datetime


class LLMProvider(ABC):
    """仅提供局部智能能力，不得决定 workflow 流程。"""

    @abstractmethod
    def extract_facts(
        self,
        task_id: str,
        company_name: str,
        question: str,
        chunks: list[EvidenceChunkRead],
    ) -> list[ExtractedFactCreate]:
        raise NotImplementedError

    @abstractmethod
    def analyze_risks(
        self,
        company_name: str,
        question: str,
        facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_report(
        self,
        task: ResearchTaskRead,
        verified_facts: list[ExtractedFactRead],
        conflicted_facts: list[ExtractedFactRead],
        insufficient_facts: list[ExtractedFactRead],
        verification_results: list[VerificationResultRead],
        risk_analysis: str,
        citations: list[Citation],
        outdated_facts: list[ExtractedFactRead] | None = None,
        rejected_facts: list[ExtractedFactRead] | None = None,
        core_facts: list[ExtractedFactRead] | None = None,
        supporting_facts: list[ExtractedFactRead] | None = None,
        relevance_intents: list[str] | None = None,
    ) -> ReportCreate:
        raise NotImplementedError

    @abstractmethod
    def check_compliance(self, text: str) -> ComplianceCheckResult:
        raise NotImplementedError
