"""阶段 2 收口：RAG 组件闭环集成测试（不改阶段 1 主链）。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.init_db import get_default_user
from app.db.models import EvidenceChunk, ResearchTask, Source
from app.db.models.source import SourceType
from app.providers.embedding.mock_provider import MockEmbeddingProvider
from app.services.embedding import EmbeddingService
from app.services.ingestion import IngestionService
from app.services.report_grounding import ReportGroundingService
from app.services.retrieval import RetrievalService
from app.vectorstores import InMemoryVectorStore, VectorRecord
from sqlalchemy.orm import Session as OrmSession


def _make_task_source(db: OrmSession, company: str, raw: str) -> tuple[str, str]:
    user = get_default_user(db)
    task = ResearchTask(user_id=user.id, company_name=company, question="阶段2 闭环验证")
    db.add(task)
    db.commit()
    db.refresh(task)
    src = Source(
        task_id=task.id,
        title=f"{company} 公告",
        url=f"https://example.com/{company}",
        source_type=SourceType.ANNOUNCEMENT,
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime.now(timezone.utc),
        raw_content=raw,
    )
    db.add(src)
    db.commit()
    db.refresh(src)
    return task.id, src.id


def _index_task_chunks(
    db: OrmSession,
    *,
    task_id: str,
    provider: MockEmbeddingProvider,
    store: InMemoryVectorStore,
) -> list[EvidenceChunk]:
    chunks = (
        db.query(EvidenceChunk)
        .filter(EvidenceChunk.task_id == task_id)
        .order_by(EvidenceChunk.source_id, EvidenceChunk.chunk_index)
        .all()
    )
    emb = EmbeddingService(db, provider).embed_and_persist_ids(chunks)
    recs = [
        VectorRecord(
            chunk_id=item.chunk_id,
            source_id=next(ch.source_id for ch in chunks if ch.id == item.chunk_id),
            task_id=task_id,
            embedding=item.vector,
            metadata={"embedding_id": item.embedding_id, "dimension": item.dimension},
        )
        for item in emb
    ]
    store.add_embeddings(recs)
    return chunks


def test_phase2_pipeline_closed_loop_task_isolation_and_grounding(db: OrmSession) -> None:
    # task A
    task_a, source_a = _make_task_source(
        db,
        "任务A",
        "公司披露研发投入增加，供应链波动与成本波动是近期风险。",
    )
    ing = IngestionService(db)
    chunks_a = ing.ingest_chunks_for_source(task_a, source_a, chunk_size=32, chunk_overlap=0)
    db.commit()
    assert len(chunks_a) >= 1

    # task B
    task_b, source_b = _make_task_source(
        db,
        "任务B",
        "另一家公司强调海外扩张节奏和渠道执行问题。",
    )
    ing.ingest_chunks_for_source(task_b, source_b, chunk_size=32, chunk_overlap=0)
    db.commit()

    provider = MockEmbeddingProvider(dimension=8)
    store = InMemoryVectorStore()
    _ = _index_task_chunks(db, task_id=task_a, provider=provider, store=store)
    _ = _index_task_chunks(db, task_id=task_b, provider=provider, store=store)

    # 2.D retrieval with task isolation
    retrieved = RetrievalService(db).retrieve_for_task(
        task_id=task_a,
        query="研发投入和风险",
        top_k=5,
        embedding_provider=provider,
        vector_store=store,
    )
    assert retrieved
    assert all(item.task_id == task_a for item in retrieved)

    # 2.E grounding
    grounding = ReportGroundingService().build_grounded_section(
        query="研发与风险",
        evidences=retrieved,
        max_items=3,
    )
    assert grounding.citations
    # citation 必须真实可追溯
    for cit in grounding.citations:
        ch = db.get(EvidenceChunk, cit.chunk_id)
        src = db.get(Source, cit.source_id)
        assert ch is not None
        assert src is not None
        assert ch.task_id == task_a


def test_phase2_pipeline_no_evidence_no_fake_citation(db: OrmSession) -> None:
    # 构造任务与 source，但不做向量索引 -> retrieval 为空
    task_id, source_id = _make_task_source(
        db,
        "空证据任务",
        "仅用于无命中场景验证。",
    )
    IngestionService(db).ingest_chunks_for_source(task_id, source_id, chunk_size=20, chunk_overlap=0)
    db.commit()

    provider = MockEmbeddingProvider(dimension=8)
    store = InMemoryVectorStore()  # 空库
    retrieved = RetrievalService(db).retrieve_for_task(
        task_id=task_id,
        query="不存在的关键词",
        top_k=5,
        embedding_provider=provider,
        vector_store=store,
    )
    assert retrieved == []

    section = ReportGroundingService().build_grounded_section(
        query="不存在的关键词",
        evidences=retrieved,
    )
    assert "证据不足" in section.content
    assert section.citations == []

