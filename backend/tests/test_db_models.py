"""ORM 模型冒烟测试。

目的：
1. 确认所有 9 张表能被 create_all 建出。
2. 确认插入主链路记录（user → session → task → source → chunk → fact → verification → report）成功。
3. 确认 relationships 双向可达。
4. 确认级联删除：删 task 时，下游记录全部清理，但 user / session 保留。
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.init_db import ensure_default_user
from app.db.models import (
    ComplianceStatus,
    EvidenceChunk,
    ExtractedFact,
    Message,
    MessageRole,
    Report,
    ResearchTask,
    Session,
    Source,
    SourceType,
    TaskStatus,
    User,
    VerificationResult,
    VerificationStatus,
)
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession


def _build_full_chain(db: OrmSession) -> ResearchTask:
    """构造一条完整的 user → ... → report 链路用于断言。"""
    user = ensure_default_user(db)

    sess = Session(user_id=user.id)
    db.add(sess)
    db.flush()

    task = ResearchTask(
        user_id=user.id,
        session_id=sess.id,
        company_name="测试科技股份有限公司",
        question="该公司近三年的研发投入变化和潜在经营风险？",
        status=TaskStatus.RUNNING,
    )
    db.add(task)
    db.flush()

    source = Source(
        task_id=task.id,
        title="2023年度报告（节选）",
        url="https://example.com/annual-2023.pdf",
        source_type=SourceType.ANNUAL_REPORT,
        published_at=datetime(2024, 4, 30, tzinfo=timezone.utc),
        retrieved_at=datetime.now(tz=timezone.utc),
        raw_content="2023 年公司研发投入为 X 亿元，同比增长 Y%。",
        credibility_score=0.85,
    )
    db.add(source)
    db.flush()

    chunk = EvidenceChunk(
        source_id=source.id,
        task_id=task.id,
        chunk_index=0,
        text="2023 年公司研发投入为 X 亿元，同比增长 Y%。",
        chunk_metadata={"section": "研发投入"},
    )
    db.add(chunk)
    db.flush()

    fact = ExtractedFact(
        task_id=task.id,
        source_id=source.id,
        chunk_id=chunk.id,
        claim="公司2023年研发投入为X亿元",
        metric_name="R&D expenditure",
        value="X 亿元",
        period="2023",
        confidence=0.82,
    )
    db.add(fact)
    db.flush()

    ver = VerificationResult(
        fact_id=fact.id,
        task_id=task.id,
        status=VerificationStatus.VERIFIED,
        confidence=0.87,
        supporting_sources=[source.id],
        conflicting_sources=[],
        reason="年报与公告数据一致（mock）",
    )
    db.add(ver)
    db.flush()

    report = Report(
        task_id=task.id,
        title="测试科技股份有限公司 —— 公开信息研究报告（mock）",
        content="# 摘要\n这是 mock 报告内容。",
        citations=[
            {
                "chunk_id": chunk.id,
                "source_id": source.id,
                "url": source.url,
                "title": source.title,
                "retrieved_at": source.retrieved_at.isoformat(),
            }
        ],
        compliance_status=ComplianceStatus.SKIPPED,
    )
    db.add(report)

    task.status = TaskStatus.COMPLETED
    db.commit()
    db.refresh(task)
    return task


def test_default_user_bootstrap_idempotent(db: OrmSession) -> None:
    u1 = ensure_default_user(db)
    u2 = ensure_default_user(db)
    assert u1.id == u2.id
    assert u1.username == "default_user"


def test_full_research_chain_persisted(db: OrmSession) -> None:
    task = _build_full_chain(db)

    fetched = db.scalar(select(ResearchTask).where(ResearchTask.id == task.id))
    assert fetched is not None
    assert fetched.status == TaskStatus.COMPLETED
    assert len(fetched.sources) == 1
    assert len(fetched.evidence_chunks) == 1
    assert len(fetched.extracted_facts) == 1
    assert len(fetched.verification_results) == 1
    assert fetched.report is not None
    assert fetched.report.compliance_status == ComplianceStatus.SKIPPED
    assert fetched.report.citations[0]["chunk_id"] == fetched.evidence_chunks[0].id


def test_relationships_back_populates(db: OrmSession) -> None:
    task = _build_full_chain(db)
    fact = task.extracted_facts[0]

    # 反向可达
    assert fact.task.id == task.id
    assert fact.source.id == task.sources[0].id
    assert fact.chunk.id == task.evidence_chunks[0].id
    assert fact.verification is not None
    assert fact.verification.status == VerificationStatus.VERIFIED


def test_cascade_delete_task_cleans_downstream_only(db: OrmSession) -> None:
    task = _build_full_chain(db)
    task_id = task.id
    user_id = task.user_id

    db.delete(task)
    db.commit()

    # 下游全清
    assert db.scalar(select(Source).where(Source.task_id == task_id)) is None
    assert db.scalar(select(EvidenceChunk).where(EvidenceChunk.task_id == task_id)) is None
    assert db.scalar(select(ExtractedFact).where(ExtractedFact.task_id == task_id)) is None
    assert (
        db.scalar(select(VerificationResult).where(VerificationResult.task_id == task_id)) is None
    )
    assert db.scalar(select(Report).where(Report.task_id == task_id)) is None

    # User 保留（只删任务，不删用户）
    assert db.scalar(select(User).where(User.id == user_id)) is not None


def test_message_attached_to_session(db: OrmSession) -> None:
    user = ensure_default_user(db)
    sess = Session(user_id=user.id)
    db.add(sess)
    db.flush()

    msg = Message(session_id=sess.id, role=MessageRole.USER, content="你好")
    db.add(msg)
    db.commit()
    db.refresh(sess)

    assert len(sess.messages) == 1
    assert sess.messages[0].role == MessageRole.USER
