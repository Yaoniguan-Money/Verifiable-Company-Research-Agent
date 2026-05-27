"""阶段 2.D：RetrievalService 测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.init_db import get_default_user
from app.db.models import EvidenceChunk, Report, ResearchTask, Source
from app.db.models.source import SourceType
from app.providers.embedding.mock_provider import MockEmbeddingProvider
from app.schemas.retrieval import RetrievedEvidence
from app.services.retrieval import RetrievalService
from app.vectorstores import InMemoryVectorStore, VectorRecord
from sqlalchemy.orm import Session as OrmSession


def _seed_task_with_chunks(
    db: OrmSession,
    *,
    company: str,
    texts: list[str],
) -> tuple[str, list[EvidenceChunk]]:
    u = get_default_user(db)
    t = ResearchTask(user_id=u.id, company_name=company, question="Q")
    db.add(t)
    db.commit()
    db.refresh(t)
    s = Source(
        task_id=t.id,
        title=f"{company} 来源",
        url=f"https://example.com/{company}",
        source_type=SourceType.NEWS,
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime.now(timezone.utc),
        raw_content="seed",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    chunks: list[EvidenceChunk] = []
    for i, txt in enumerate(texts):
        ch = EvidenceChunk(
            source_id=s.id,
            task_id=t.id,
            chunk_index=i,
            text=txt,
            chunk_metadata={"tag": f"{company}-{i}"},
            embedding_id=None,
        )
        db.add(ch)
        chunks.append(ch)
    db.commit()
    for ch in chunks:
        db.refresh(ch)
    return t.id, chunks


def _build_store(task_id: str, chunks: list[EvidenceChunk], p: MockEmbeddingProvider) -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    records = [
        VectorRecord(
            chunk_id=ch.id,
            source_id=ch.source_id,
            task_id=task_id,
            embedding=p.embed_query(ch.text),
            metadata={"embedding_id": p.embedding_id_for_text(ch.text)},
        )
        for ch in chunks
    ]
    store.add_embeddings(records)
    return store


def test_retrieve_for_task_returns_structured_evidence(db: OrmSession) -> None:
    tid, chunks = _seed_task_with_chunks(
        db,
        company="甲",
        texts=["研发投入持续增长，技术积累增强", "供应链波动带来短期交付压力"],
    )
    p = MockEmbeddingProvider(dimension=8)
    store = _build_store(tid, chunks, p)

    svc = RetrievalService(db)
    out = svc.retrieve_for_task(
        task_id=tid,
        query="研发投入增长情况",
        top_k=2,
        embedding_provider=p,
        vector_store=store,
    )
    assert 1 <= len(out) <= 2
    first = out[0]
    assert isinstance(first, RetrievedEvidence)
    assert first.chunk_id
    assert first.source_id
    assert first.task_id == tid
    assert first.text
    assert isinstance(first.score, float)
    assert first.source_title
    assert first.source_url
    assert first.metadata is not None


def test_top_k_applies(db: OrmSession) -> None:
    tid, chunks = _seed_task_with_chunks(db, company="乙", texts=["A", "B", "C"])
    p = MockEmbeddingProvider(dimension=8)
    store = _build_store(tid, chunks, p)
    out = RetrievalService(db).retrieve_for_task(
        task_id=tid,
        query="A",
        top_k=1,
        embedding_provider=p,
        vector_store=store,
    )
    assert len(out) == 1


def test_task_id_isolation(db: OrmSession) -> None:
    t1, c1 = _seed_task_with_chunks(db, company="T1", texts=["同题材文本-任务一"])
    t2, c2 = _seed_task_with_chunks(db, company="T2", texts=["同题材文本-任务二"])
    p = MockEmbeddingProvider(dimension=8)
    store = InMemoryVectorStore()
    for tid, chunks in ((t1, c1), (t2, c2)):
        store.add_embeddings(
            [
                VectorRecord(
                    chunk_id=ch.id,
                    source_id=ch.source_id,
                    task_id=tid,
                    embedding=p.embed_query(ch.text),
                    metadata={},
                )
                for ch in chunks
            ]
        )

    out = RetrievalService(db).retrieve_for_task(
        task_id=t1,
        query="同题材文本",
        top_k=5,
        embedding_provider=p,
        vector_store=store,
    )
    assert out
    assert all(x.task_id == t1 for x in out)


def test_blank_query_raises(db: OrmSession) -> None:
    p = MockEmbeddingProvider()
    out = InMemoryVectorStore()
    with pytest.raises(ValueError, match="query 不能为空"):
        RetrievalService(db).retrieve_for_task(
            task_id="t",
            query="  \n",
            top_k=3,
            embedding_provider=p,
            vector_store=out,
        )


def test_top_k_non_positive_returns_empty(db: OrmSession) -> None:
    p = MockEmbeddingProvider()
    out = RetrievalService(db).retrieve_for_task(
        task_id="t",
        query="x",
        top_k=0,
        embedding_provider=p,
        vector_store=InMemoryVectorStore(),
    )
    assert out == []


def test_empty_vector_store_returns_empty(db: OrmSession) -> None:
    p = MockEmbeddingProvider()
    out = RetrievalService(db).retrieve_for_task(
        task_id="t",
        query="x",
        top_k=3,
        embedding_provider=p,
        vector_store=InMemoryVectorStore(),
    )
    assert out == []


def test_vector_hit_but_chunk_missing_in_db_is_skipped(db: OrmSession) -> None:
    tid, chunks = _seed_task_with_chunks(db, company="丙", texts=["真实存在"])
    p = MockEmbeddingProvider(dimension=8)
    store = _build_store(tid, chunks, p)
    # 注入一个 DB 中不存在的 chunk_id
    store.add_embeddings(
        [
            VectorRecord(
                chunk_id="not-in-db",
                source_id="missing-source",
                task_id=tid,
                embedding=p.embed_query("真实存在"),
                metadata={},
            )
        ]
    )
    out = RetrievalService(db).retrieve_for_task(
        task_id=tid,
        query="真实存在",
        top_k=5,
        embedding_provider=p,
        vector_store=store,
    )
    assert out
    assert all(x.chunk_id != "not-in-db" for x in out)


def test_source_info_backfilled(db: OrmSession) -> None:
    tid, chunks = _seed_task_with_chunks(db, company="丁", texts=["供应链风险"])
    p = MockEmbeddingProvider(dimension=8)
    store = _build_store(tid, chunks, p)
    out = RetrievalService(db).retrieve_for_task(
        task_id=tid,
        query="供应链",
        top_k=1,
        embedding_provider=p,
        vector_store=store,
    )
    assert len(out) == 1
    row = out[0]
    assert row.source_title.endswith("来源")
    assert row.source_type
    assert row.retrieved_at


def test_retrieval_service_does_not_generate_report(db: OrmSession) -> None:
    tid, chunks = _seed_task_with_chunks(db, company="戊", texts=["文本"])
    p = MockEmbeddingProvider(dimension=8)
    store = _build_store(tid, chunks, p)
    svc = RetrievalService(db)
    _ = svc.retrieve_for_task(
        task_id=tid,
        query="文本",
        top_k=1,
        embedding_provider=p,
        vector_store=store,
    )
    assert db.query(Report).filter(Report.task_id == tid).count() == 0

