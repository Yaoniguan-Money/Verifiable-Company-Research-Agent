from __future__ import annotations

from sqlalchemy.orm import Session

from app.providers.factory import ProviderFactory
from app.providers.llm import LLMProvider
from app.repositories import ResearchArtifactRepository
from app.schemas.common import ComplianceStatus
from app.schemas.report import ReportRead


class ReportOutputService:
    """Read reports through the same final-output compliance boundary."""

    def __init__(self, db: Session, llm_provider: LLMProvider | None = None) -> None:
        self.db = db
        self.llm_provider = llm_provider or ProviderFactory().create_llm_provider()
        self.artifacts = ResearchArtifactRepository(db)

    def get_report(self, task_id: str) -> ReportRead | None:
        row = self.artifacts.get_report_by_task_id(task_id)
        return ReportRead.model_validate(row) if row else None

    def get_report_for_output(self, task_id: str) -> ReportRead | None:
        report = self.get_report(task_id)
        if report is None:
            return None
        check = self.llm_provider.check_compliance(report.content)
        if check.status == ComplianceStatus.PASSED:
            return report
        return report.model_copy(
            update={
                "content": check.rewritten_text or report.content,
                "compliance_status": check.status,
            }
        )
