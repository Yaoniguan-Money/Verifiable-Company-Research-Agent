from __future__ import annotations

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.db.models import (
    EvidenceChunk,
    ExtractedFact,
    Report,
    ResearchTask,
    Source,
    VerificationResult,
)
from app.db.models import (
    Session as SessionOrm,
)
from app.db.models import (
    TaskStatus as TaskStatusORM,
)
from app.schemas.report import ReportCreate
from app.schemas.source import SourceCreate


class ResearchTaskRepository:
    """Persistence boundary for research task lifecycle queries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        user_id: str,
        company_name: str,
        question: str,
        session_id: str | None,
    ) -> ResearchTask:
        task = ResearchTask(
            user_id=user_id,
            session_id=session_id,
            company_name=company_name,
            question=question,
            status=TaskStatusORM.CREATED,
            error_message=None,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return task

    def get(self, task_id: str) -> ResearchTask | None:
        return self.db.query(ResearchTask).filter(ResearchTask.id == task_id).one_or_none()

    def list_recent(self, *, limit: int = 50) -> list[ResearchTask]:
        return (
            self.db.query(ResearchTask)
            .order_by(ResearchTask.updated_at.desc())
            .limit(max(1, min(limit, 200)))
            .all()
        )

    def session_belongs_to_user(self, *, session_id: str, user_id: str) -> bool:
        sess = self.db.query(SessionOrm).filter(SessionOrm.id == session_id).one_or_none()
        return sess is not None and sess.user_id == user_id

    def claim_for_run(
        self,
        *,
        task_id: str,
        runnable_statuses: tuple[TaskStatusORM, ...],
    ) -> ResearchTask | None:
        result = self.db.execute(
            update(ResearchTask)
            .where(
                ResearchTask.id == task_id,
                ResearchTask.status.in_(runnable_statuses),
            )
            .values(status=TaskStatusORM.RUNNING, error_message=None)
        )
        if result.rowcount != 1:
            self.db.rollback()
            return None
        self.db.commit()
        return self.get(task_id)


class ResearchArtifactRepository:
    """Persistence boundary for task artifacts.

    Service 层负责业务流程；这里仅集中 ORM 查询和写入，避免查询散落到多个 service。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def delete_task_outputs(self, task_id: str) -> None:
        self.db.query(Report).filter(Report.task_id == task_id).delete(synchronize_session=False)
        self.db.query(VerificationResult).filter(
            VerificationResult.task_id == task_id
        ).delete(synchronize_session=False)
        self.db.query(ExtractedFact).filter(ExtractedFact.task_id == task_id).delete(
            synchronize_session=False
        )
        self.db.query(EvidenceChunk).filter(EvidenceChunk.task_id == task_id).delete(
            synchronize_session=False
        )
        self.db.query(Source).filter(Source.task_id == task_id).delete(synchronize_session=False)

    def add_sources(self, *, task_id: str, sources: list[SourceCreate]) -> list[Source]:
        from app.db.init_db import ensure_lightweight_schema_updates

        ensure_lightweight_schema_updates(self.db.get_bind())
        rows = [
            Source(
                task_id=task_id,
                title=item.title,
                url=item.url,
                source_type=item.source_type.value,
                published_at=item.published_at,
                retrieved_at=item.retrieved_at,
                raw_content=item.raw_content,
                credibility_score=item.credibility_score,
                source_metadata=self._source_metadata_with_disclosure_kind(item),
            )
            for item in sources
        ]
        if rows:
            self.db.add_all(rows)
        return rows

    def _source_metadata_with_disclosure_kind(self, item: SourceCreate) -> dict:
        metadata = dict(item.source_metadata or {})
        metadata.setdefault(
            "disclosure_kind",
            self._infer_disclosure_kind(
                title=item.title,
                source_type=str(getattr(item.source_type, "value", item.source_type)),
            ),
        )
        return metadata

    def _infer_disclosure_kind(self, *, title: str, source_type: str) -> str:
        text = (title or "").lower()
        if "年度报告" in text or "年报" in text or "annual" in text:
            return "annual"
        if "半年度" in text or "半年报" in text or "semi" in text:
            return "semi_annual"
        if "季度" in text or "一季报" in text or "三季报" in text or "临时" in text:
            return "interim"
        if source_type in {"news", "other"}:
            return "media"
        return "interim"

    def add_facts(self, facts: list[ExtractedFact]) -> None:
        if facts:
            self.db.add_all(facts)

    def add_verifications(self, verifications: list[VerificationResult]) -> None:
        if verifications:
            self.db.add_all(verifications)

    def add_chunk(self, chunk: EvidenceChunk) -> None:
        self.db.add(chunk)

    def add_report(self, report: ReportCreate) -> Report:
        row = Report(
            task_id=report.task_id,
            title=report.title,
            content=report.content,
            citations=[item.model_dump(mode="json") for item in report.citations],
            compliance_status=report.compliance_status.value,
        )
        self.db.add(row)
        return row

    def get_report_by_task_id(self, task_id: str) -> Report | None:
        return self.db.query(Report).filter(Report.task_id == task_id).one_or_none()

    def get_source(self, source_id: str) -> Source | None:
        return self.db.query(Source).filter(Source.id == source_id).one_or_none()

    def list_sources(self, task_id: str) -> list[Source]:
        return self.db.query(Source).filter(Source.task_id == task_id).order_by(Source.created_at).all()

    def list_chunks(self, task_id: str) -> list[EvidenceChunk]:
        return (
            self.db.query(EvidenceChunk)
            .filter(EvidenceChunk.task_id == task_id)
            .order_by(EvidenceChunk.source_id, EvidenceChunk.chunk_index)
            .all()
        )

    def list_chunks_by_ids(self, *, task_id: str, chunk_ids: list[str]) -> list[EvidenceChunk]:
        if not chunk_ids:
            return []
        return (
            self.db.query(EvidenceChunk)
            .filter(EvidenceChunk.task_id == task_id, EvidenceChunk.id.in_(chunk_ids))
            .all()
        )

    def list_sources_by_ids(self, source_ids: list[str]) -> list[Source]:
        if not source_ids:
            return []
        return self.db.query(Source).filter(Source.id.in_(source_ids)).all()

    def list_facts(self, task_id: str) -> list[ExtractedFact]:
        return (
            self.db.query(ExtractedFact)
            .filter(ExtractedFact.task_id == task_id)
            .order_by(ExtractedFact.created_at)
            .all()
        )

    def list_verifications(self, task_id: str) -> list[VerificationResult]:
        return (
            self.db.query(VerificationResult)
            .filter(VerificationResult.task_id == task_id)
            .order_by(VerificationResult.created_at)
            .all()
        )

    def source_context(self, task_id: str) -> dict[str, tuple[datetime | None, float | None, dict | None]]:
        return {
            item.id: (item.published_at, item.credibility_score, item.source_metadata)
            for item in self.list_sources(task_id)
        }

    def source_map(self, task_id: str) -> dict[str, Source]:
        return {item.id: item for item in self.list_sources(task_id)}

    def chunk_map(self, task_id: str) -> dict[str, EvidenceChunk]:
        return {item.id: item for item in self.list_chunks(task_id)}

    def delete_chunks_for_source(self, *, task_id: str, source_id: str) -> None:
        self.db.query(EvidenceChunk).filter(
            EvidenceChunk.source_id == source_id,
            EvidenceChunk.task_id == task_id,
        ).delete(synchronize_session=False)
