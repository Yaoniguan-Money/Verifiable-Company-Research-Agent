"""阶段 2.A：ChunkingService / IngestionService。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.init_db import get_default_user
from app.db.models import EvidenceChunk, ResearchTask, Source
from app.schemas.chunk import EvidenceChunkRead
from app.schemas.common import SourceType
from app.services.chunking import ChunkingService
from app.services.ingestion import IngestionService
from sqlalchemy.orm import Session as OrmSession

# --- ChunkingService ---


def test_chunking_long_text_produces_multiple_chunks() -> None:
    raw = "啊" * 500
    svc = ChunkingService()
    now = datetime.now(timezone.utc)
    parts = svc.split(
        raw,
        chunk_size=100,
        chunk_overlap=10,
        source_title="t",
        source_url="https://u",
        source_type="news",
        retrieved_at=now,
    )
    assert len(parts) >= 2
    assert all(p.text for p in parts)
    for i, p in enumerate(parts):
        assert p.chunk_index == i
    assert "source_title" in parts[0].metadata
    assert parts[0].metadata.get("chunk_size") == 100
    assert "strategy" in parts[0].metadata


def test_chunking_empty_returns_empty() -> None:
    svc = ChunkingService()
    assert svc.split("", chunk_size=100, chunk_overlap=0, source_title="x", source_type="a") == []
    assert svc.split("   \n  ", chunk_size=100, chunk_overlap=0, source_title="x", source_type="a") == []


def test_chunking_non_empty_starts_index_at_zero() -> None:
    svc = ChunkingService()
    parts = svc.split("短文本", chunk_size=50, chunk_overlap=0, source_title="t", source_type=SourceType.NEWS.value)
    assert len(parts) == 1
    assert parts[0].chunk_index == 0
    assert parts[0].text == "短文本"


# --- IngestionService ---


def _make_task_with_source(db: OrmSession, raw: str) -> tuple[str, str]:
    u = get_default_user(db)
    t = ResearchTask(
        user_id=u.id,
        company_name="测公司",
        question="问?",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    tid = t.id
    s = Source(
        task_id=tid,
        title="测来源",
        url="https://ex.test/doc",
        source_type=SourceType.ANNOUNCEMENT,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime.now(timezone.utc),
        raw_content=raw,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return tid, s.id


def test_ingestion_writes_multiple_chunks_with_metadata(
    db: OrmSession,
) -> None:
    raw = "句" * 300
    tid, sid = _make_task_with_source(db, raw)
    ing = IngestionService(db)
    rows = ing.ingest_chunks_for_source(tid, sid, chunk_size=100, chunk_overlap=0)
    assert len(rows) >= 2
    for r in rows:
        assert r.task_id == tid
        assert r.source_id == sid
    indices = [r.chunk_index for r in db.query(EvidenceChunk).filter(EvidenceChunk.source_id == sid).all()]
    assert indices == list(range(len(indices)))
    for row in rows:
        assert row.chunk_metadata is not None
        # 规范：见 EvidenceChunkRead 类 docstring。禁止 model_validate(orm_row)；显式传 metadata=chunk_metadata 或 dict
        read = EvidenceChunkRead(
            id=row.id,
            source_id=row.source_id,
            task_id=row.task_id,
            chunk_index=row.chunk_index,
            text=row.text,
            metadata=row.chunk_metadata,
            embedding_id=row.embedding_id,
            created_at=row.created_at,
        )
        assert read.metadata is not None
        assert read.metadata.get("strategy") in {"char_window", "section_aware", "recursive", "fixed_window"}
        assert "source_title" in read.metadata
        same = EvidenceChunkRead.model_validate(
            {
                "id": row.id,
                "source_id": row.source_id,
                "task_id": row.task_id,
                "chunk_index": row.chunk_index,
                "text": row.text,
                "metadata": row.chunk_metadata,
                "embedding_id": row.embedding_id,
                "created_at": row.created_at,
            }
        )
        assert same.metadata == read.metadata


def test_ingestion_source_missing_raises(db: OrmSession) -> None:
    t, _ = _make_task_with_source(db, "短")
    ing = IngestionService(db)
    with pytest.raises(ValueError, match="资料来源不存在"):
        ing.ingest_chunks_for_source(t, "00000000-0000-0000-0000-000000000000")


def test_ingestion_task_mismatch_raises(db: OrmSession) -> None:
    t1, s1 = _make_task_with_source(db, "短文本一")
    t2, _ = _make_task_with_source(db, "短文本二")
    # s1 属于 t1
    ing = IngestionService(db)
    with pytest.raises(ValueError, match="任务 ID 不一致"):
        ing.ingest_chunks_for_source(t2, s1)


def test_ingestion_re_run_replaces_not_duplicates(db: OrmSession) -> None:
    long = "可重复" * 200
    tid, sid = _make_task_with_source(db, long)
    ing = IngestionService(db)
    ing.ingest_chunks_for_source(tid, sid, chunk_size=80, chunk_overlap=0)
    n1 = db.query(EvidenceChunk).filter(EvidenceChunk.source_id == sid).count()
    assert n1 >= 1
    ing.ingest_chunks_for_source(tid, sid, chunk_size=80, chunk_overlap=0)
    n2 = db.query(EvidenceChunk).filter(EvidenceChunk.source_id == sid).count()
    assert n1 == n2
    all_rows = (
        db.query(EvidenceChunk)
        .filter(EvidenceChunk.source_id == sid, EvidenceChunk.task_id == tid)
        .order_by(EvidenceChunk.chunk_index)
        .all()
    )
    assert len({r.chunk_index for r in all_rows}) == len(all_rows)
