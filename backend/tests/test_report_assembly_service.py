from __future__ import annotations

from app.db.init_db import get_default_user
from app.db.models import ExtractedFact, ResearchTask, VerificationResult
from app.db.models.research_task import TaskStatus
from app.services.report_assembly import ReportAssemblyService
from sqlalchemy.orm import Session as OrmSession


def _make_task(db: OrmSession) -> ResearchTask:
    user = get_default_user(db)
    task = ResearchTask(
        user_id=user.id,
        company_name="Assembly Co",
        question="Check report buckets",
        status=TaskStatus.COMPLETED,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _add_fact_with_verification(
    db: OrmSession,
    *,
    task: ResearchTask,
    status: str,
    source_id: str,
    chunk_id: str,
) -> None:
    fact = ExtractedFact(
        task_id=task.id,
        claim=f"{status} claim",
        metric_name="revenue",
        value="100",
        period="2024",
        source_id=source_id,
        chunk_id=chunk_id,
        confidence=0.8,
    )
    db.add(fact)
    db.flush()
    db.add(
        VerificationResult(
            fact_id=fact.id,
            task_id=task.id,
            status=status,
            confidence=0.8,
            supporting_sources=[source_id],
            conflicting_sources=["other_source"] if status == "conflicted" else [],
            reason=f"{status} reason",
        )
    )


def test_report_assembly_buckets_all_verification_statuses(db: OrmSession) -> None:
    task = _make_task(db)
    for idx, status in enumerate(
        ["verified", "conflicted", "insufficient", "outdated", "rejected"],
        start=1,
    ):
        _add_fact_with_verification(
            db,
            task=task,
            status=status,
            source_id=f"source_{idx}",
            chunk_id=f"chunk_{idx}",
        )
    db.commit()
    db.refresh(task)

    report = ReportAssemblyService(db).build_report(
        task=task,
        risk_analysis="No additional risk analysis.",
        citations=[],
    )

    assert "verified claim" in report.content
    assert "conflicted claim" in report.content
    assert "insufficient claim" in report.content
    assert "status=outdated" in report.content
    assert "outdated claim" in report.content
    assert "status=rejected" in report.content
    assert "rejected claim" in report.content
