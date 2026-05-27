"""PostgreSQL 向量存储：优先 pgvector HNSW，回退 JSON+cosine。"""

from __future__ import annotations

import json
import uuid
from math import sqrt
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine, inspect, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.vectorstores.base import VectorRecord, VectorSearchResult, VectorStore


class _Base(DeclarativeBase):
    pass


class _EvidenceVectorRow(_Base):
    __tablename__ = "evidence_vectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    embedding: Mapped[str] = mapped_column(Text, nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=True)


class PgVectorStore(VectorStore):
    def __init__(self, database_url: str) -> None:
        if not database_url.startswith("postgresql"):
            raise ValueError("PgVectorStore 需要 postgresql:// 或 postgresql+psycopg2:// URL")
        self._engine = create_engine(database_url, future=True, pool_pre_ping=True)
        self._session_factory = sessionmaker(bind=self._engine, autoflush=False, expire_on_commit=False)
        self._hnsw_enabled = False
        self._ensure_table()

    @property
    def dimension(self) -> int | None:
        with self._session_factory() as session:
            row = session.execute(
                text("SELECT dimension FROM evidence_vectors ORDER BY created_at DESC NULLS LAST LIMIT 1")
            ).first()
        return int(row[0]) if row else None

    def add_embeddings(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        dimension = self._validate_batch(records)
        with self._session_factory() as session:
            for rec in records:
                payload = json.dumps(rec.embedding, ensure_ascii=False)
                row = session.scalar(
                    select(_EvidenceVectorRow).where(_EvidenceVectorRow.chunk_id == rec.chunk_id)
                )
                if row is None:
                    row = _EvidenceVectorRow(
                        id=str(uuid.uuid4()),
                        chunk_id=rec.chunk_id,
                        task_id=rec.task_id,
                        source_id=rec.source_id,
                        embedding=payload,
                        dimension=dimension,
                        metadata_json=rec.metadata,
                    )
                    session.add(row)
                else:
                    row.task_id = rec.task_id
                    row.source_id = rec.source_id
                    row.embedding = payload
                    row.dimension = dimension
                    row.metadata_json = rec.metadata
                if self._hnsw_enabled:
                    vec = "[" + ",".join(str(float(x)) for x in rec.embedding) + "]"
                    session.execute(
                        text(
                            """
                            UPDATE evidence_vectors
                            SET embedding_vec = CAST(:vec AS vector)
                            WHERE chunk_id = :chunk_id
                            """
                        ),
                        {"vec": vec, "chunk_id": rec.chunk_id},
                    )
            session.commit()
        return len(records)

    def similarity_search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        task_id: str | None = None,
    ) -> list[VectorSearchResult]:
        if top_k <= 0 or not query_embedding:
            return []
        if self._hnsw_enabled:
            return self._similarity_search_hnsw(query_embedding, top_k=top_k, task_id=task_id)
        return self._similarity_search_json(query_embedding, top_k=top_k, task_id=task_id)

    def _similarity_search_hnsw(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        task_id: str | None,
    ) -> list[VectorSearchResult]:
        vec = "[" + ",".join(str(float(x)) for x in query_embedding) + "]"
        sql = """
            SELECT chunk_id, source_id, task_id, metadata_json,
                   1 - (embedding_vec <=> CAST(:q AS vector)) AS score
            FROM evidence_vectors
            WHERE embedding_vec IS NOT NULL
        """
        params: dict[str, Any] = {"q": vec, "k": top_k}
        if task_id is not None:
            sql += " AND task_id = :task_id"
            params["task_id"] = task_id
        sql += " ORDER BY embedding_vec <=> CAST(:q AS vector) LIMIT :k"
        with self._session_factory() as session:
            rows = session.execute(text(sql), params).mappings().all()
        return [
            VectorSearchResult(
                chunk_id=str(r["chunk_id"]),
                source_id=str(r["source_id"]),
                task_id=str(r["task_id"]),
                score=float(r["score"]),
                metadata=r["metadata_json"] or {},
            )
            for r in rows
        ]

    def _similarity_search_json(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
        task_id: str | None,
    ) -> list[VectorSearchResult]:
        rows = self._load_rows(task_id=task_id)
        if not rows:
            return []
        expected_dim = int(rows[0].dimension)
        if len(query_embedding) != expected_dim:
            raise ValueError(
                f"query embedding 维度不一致：期望 {expected_dim}，实际 {len(query_embedding)}"
            )
        scored: list[VectorSearchResult] = []
        for row in rows:
            embedding = [float(item) for item in json.loads(row.embedding)]
            scored.append(
                VectorSearchResult(
                    chunk_id=row.chunk_id,
                    source_id=row.source_id,
                    task_id=row.task_id,
                    score=self._cosine(query_embedding, embedding),
                    metadata=row.metadata_json or {},
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def delete(self, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0
        with self._session_factory() as session:
            deleted = 0
            for cid in chunk_ids:
                row = session.scalar(
                    select(_EvidenceVectorRow).where(_EvidenceVectorRow.chunk_id == cid)
                )
                if row is not None:
                    session.delete(row)
                    deleted += 1
            session.commit()
            return deleted

    def delete_task(self, task_id: str) -> int:
        with self._session_factory() as session:
            rows = list(
                session.scalars(
                    select(_EvidenceVectorRow).where(_EvidenceVectorRow.task_id == task_id)
                )
            )
            for row in rows:
                session.delete(row)
            session.commit()
            return len(rows)

    def clear(self) -> None:
        with self._session_factory() as session:
            session.execute(text("DELETE FROM evidence_vectors"))
            session.commit()

    def _ensure_table(self) -> None:
        with self._engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        _Base.metadata.create_all(self._engine)
        inspector = inspect(self._engine)
        if "evidence_vectors" in inspector.get_table_names():
            cols = {c["name"] for c in inspector.get_columns("evidence_vectors")}
            self._hnsw_enabled = "embedding_vec" in cols

    def _load_rows(self, *, task_id: str | None) -> list[_EvidenceVectorRow]:
        with self._session_factory() as session:
            stmt = select(_EvidenceVectorRow)
            if task_id is not None:
                stmt = stmt.where(_EvidenceVectorRow.task_id == task_id)
            return list(session.scalars(stmt))

    @staticmethod
    def _validate_batch(records: list[VectorRecord]) -> int:
        dimension = len(records[0].embedding)
        if dimension <= 0:
            raise ValueError("record embedding 不能为空")
        for rec in records:
            if len(rec.embedding) != dimension:
                raise ValueError("record embedding 维度不一致")
        return dimension

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        num = sum(x * y for x, y in zip(a, b, strict=False))
        na = sqrt(sum(x * x for x in a))
        nb = sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(num / (na * nb))
