"""阶段 2.B：EmbeddingProvider / Mock / EmbeddingService，无向量库。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.init_db import get_default_user
from app.db.models import EvidenceChunk, ResearchTask, Source
from app.db.models.source import SourceType
from app.providers.embedding.base import EmbeddingProvider
from app.providers.embedding.local_hashing_provider import LocalHashingEmbeddingProvider
from app.providers.embedding.mock_provider import MockEmbeddingProvider
from app.services.embedding import EmbeddingService
from sqlalchemy.orm import Session as OrmSession


class _StubProvider(EmbeddingProvider):
    """可替换性测试用：不访问网络，固定维度、固定 ID 规则。"""

    def __init__(self, dim: int = 4) -> None:
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_query(self, text: str) -> list[float]:
        s = (text or "").strip()
        if not s:
            raise ValueError("空")
        return [float(ord(s[0 % len(s)]) % 10) / 10.0] * self._dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self.embed_query(t) for t in texts]

    def embedding_id_for_text(self, text: str) -> str:
        s = (text or "").strip()
        if not s:
            raise ValueError("空")
        return f"stub-emb-dim{self._dim}-x"


def test_mock_deterministic_same_text_same_vector() -> None:
    p = MockEmbeddingProvider(dimension=8)
    t = "可重复同一句"
    a1 = p.embed_query(t)
    a2 = p.embed_query(t)
    assert a1 == a2
    assert len(a1) == 8
    assert p.embedding_id_for_text(t) == p.embedding_id_for_text(f"  {t}  ")


def test_mock_different_texts_vectors_not_all_equal() -> None:
    p = MockEmbeddingProvider(dimension=8)
    a = p.embed_query("甲内容用于区分")
    b = p.embed_query("乙另一段不相同的文本")
    assert a != b


def test_mock_dimension_property() -> None:
    p = MockEmbeddingProvider(dimension=8)
    assert p.dimension == 8


def test_local_hashing_embedding_is_deterministic_and_normalized() -> None:
    p = LocalHashingEmbeddingProvider(dimension=64)
    text = "研发投入 增长 revenue risk"

    a = p.embed_query(text)
    b = p.embed_query(f"  {text}  ")

    assert a == b
    assert len(a) == 64
    assert p.embedding_id_for_text(text).startswith("local-hash-v1-dim64-")
    assert abs(sum(item * item for item in a) - 1.0) < 0.0001


def test_empty_documents_returns_empty_list() -> None:
    p = MockEmbeddingProvider()
    assert p.embed_documents([]) == []


def test_empty_query_raises() -> None:
    p = MockEmbeddingProvider()
    with pytest.raises(ValueError):
        p.embed_query("")
    with pytest.raises(ValueError):
        p.embed_query("  \n\t  ")


def test_documents_with_blank_item_raises() -> None:
    p = MockEmbeddingProvider()
    with pytest.raises(ValueError):
        p.embed_documents([""])
    with pytest.raises(ValueError):
        p.embed_documents(["好", "  "])


def test_embedding_service_uses_abstract_provider(db: OrmSession) -> None:
    u = get_default_user(db)
    t = ResearchTask(user_id=u.id, company_name="C", question="Q")
    db.add(t)
    db.commit()
    db.refresh(t)
    s = Source(
        task_id=t.id,
        title="T",
        url="https://x",
        source_type=SourceType.NEWS,
        published_at=datetime.now(timezone.utc),
        retrieved_at=datetime.now(timezone.utc),
        raw_content="r",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    ch = EvidenceChunk(
        source_id=s.id,
        task_id=t.id,
        chunk_index=0,
        text="显式可嵌入文本",
        chunk_metadata={"k": 1},
        embedding_id="2a-old-placeholder",  # 2.A 占位，2.B 覆盖
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)

    stub = _StubProvider(dim=4)
    svc = EmbeddingService(db, stub)
    res = svc.embed_and_persist_ids([ch])
    assert len(res) == 1
    assert res[0].dimension == 4
    assert res[0].embedding_id == "stub-emb-dim4-x"
    db.commit()
    r2 = db.get(EvidenceChunk, ch.id)
    assert r2 is not None
    assert r2.embedding_id == "stub-emb-dim4-x"
    assert r2.chunk_metadata == {"k": 1}
    assert "vector" not in (r2.chunk_metadata or {})


def test_embedding_service_mock_persist_read_after_commit(db: OrmSession) -> None:
    u = get_default_user(db)
    t = ResearchTask(user_id=u.id, company_name="C2", question="Q2")
    db.add(t)
    db.commit()
    db.refresh(t)
    s = Source(
        task_id=t.id,
        title="T2",
        url=None,
        source_type=SourceType.ANNOUNCEMENT,
        published_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime.now(timezone.utc),
        raw_content="x",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    ch = EvidenceChunk(
        source_id=s.id,
        task_id=t.id,
        chunk_index=0,
        text="同一条目用于ID一致",
        chunk_metadata={},
        embedding_id="mock-emb-old-2a-style",
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)

    mock = MockEmbeddingProvider(dimension=8)
    ev = mock.embedding_id_for_text(ch.text)
    assert ev.startswith("mock-emb-v1-dim8-")

    svc = EmbeddingService(db, mock)
    svc.embed_and_persist_ids([ch])
    db.commit()

    r = db.get(EvidenceChunk, ch.id)
    assert r is not None
    assert r.embedding_id == ev
    # 2.B 指纹；不在 chunk_metadata 中存 list[float]
    assert not any(isinstance((r.chunk_metadata or {}).get(k), list) for k in (r.chunk_metadata or {}))


def test_embed_task_id_loads_all_chunks(db: OrmSession) -> None:
    u = get_default_user(db)
    t = ResearchTask(user_id=u.id, company_name="C3", question="Q3")
    db.add(t)
    db.commit()
    db.refresh(t)
    s = Source(
        task_id=t.id,
        title="T3",
        url="u",
        source_type=SourceType.NEWS,
        published_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime.now(timezone.utc),
        raw_content="body",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    for i, piece in enumerate(["段落甲内容", "段落乙内容"]):
        db.add(
            EvidenceChunk(
                source_id=s.id,
                task_id=t.id,
                chunk_index=i,
                text=piece,
                chunk_metadata={},
            )
        )
    db.commit()

    p = MockEmbeddingProvider(dimension=8)
    svc = EmbeddingService(db, p)
    res = svc.embed_and_persist_ids_for_task(t.id)
    assert len(res) == 2
    assert {r.chunk_id for r in res} == {c.id for c in db.query(EvidenceChunk).filter(EvidenceChunk.task_id == t.id)}
