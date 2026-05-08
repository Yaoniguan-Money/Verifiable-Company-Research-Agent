"""SQLite-backed vector store for local persistent retrieval."""

from __future__ import annotations

import json
import sqlite3
from math import sqrt
from pathlib import Path
from typing import Any

from app.vectorstores.base import VectorRecord, VectorSearchResult, VectorStore


class SQLiteVectorStore(VectorStore):
    """Persist vectors in SQLite and score them locally with cosine similarity."""

    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_table()

    @property
    def dimension(self) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT dimension FROM vector_records ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return int(row[0]) if row else None

    def add_embeddings(self, records: list[VectorRecord]) -> int:
        if not records:
            return 0
        dimension = self._validate_batch(records)
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO vector_records (
                    chunk_id, source_id, task_id, embedding_json, metadata_json, dimension, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    source_id=excluded.source_id,
                    task_id=excluded.task_id,
                    embedding_json=excluded.embedding_json,
                    metadata_json=excluded.metadata_json,
                    dimension=excluded.dimension,
                    updated_at=CURRENT_TIMESTAMP
                """,
                [
                    (
                        rec.chunk_id,
                        rec.source_id,
                        rec.task_id,
                        json.dumps(rec.embedding, ensure_ascii=False),
                        json.dumps(rec.metadata, ensure_ascii=False),
                        dimension,
                    )
                    for rec in records
                ],
            )
        return len(records)

    def similarity_search(
        self,
        query_embedding: list[float],
        *,
        top_k: int = 5,
        task_id: str | None = None,
    ) -> list[VectorSearchResult]:
        if top_k <= 0:
            return []
        if not query_embedding:
            raise ValueError("query embedding 不能为空")

        rows = self._load_rows(task_id=task_id)
        if not rows:
            return []

        expected_dim = int(rows[0]["dimension"])
        if len(query_embedding) != expected_dim:
            raise ValueError(
                f"query embedding 维度不一致：期望 {expected_dim}，实际 {len(query_embedding)}"
            )

        scored: list[VectorSearchResult] = []
        for row in rows:
            embedding = [float(item) for item in json.loads(row["embedding_json"])]
            scored.append(
                VectorSearchResult(
                    chunk_id=str(row["chunk_id"]),
                    source_id=str(row["source_id"]),
                    task_id=str(row["task_id"]),
                    score=self._cosine(query_embedding, embedding),
                    metadata=self._load_metadata(str(row["metadata_json"])),
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def delete(self, chunk_ids: list[str]) -> int:
        if not chunk_ids:
            return 0
        with self._connect() as conn:
            before = conn.total_changes
            conn.executemany(
                "DELETE FROM vector_records WHERE chunk_id = ?",
                [(cid,) for cid in chunk_ids],
            )
            return conn.total_changes - before

    def delete_task(self, task_id: str) -> int:
        with self._connect() as conn:
            before = conn.total_changes
            conn.execute("DELETE FROM vector_records WHERE task_id = ?", (task_id,))
            return conn.total_changes - before

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM vector_records")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vector_records (
                    chunk_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    dimension INTEGER NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_vector_records_task_id ON vector_records(task_id)"
            )

    def _load_rows(self, *, task_id: str | None) -> list[sqlite3.Row]:
        with self._connect() as conn:
            if task_id is None:
                return list(
                    conn.execute(
                        "SELECT chunk_id, source_id, task_id, embedding_json, metadata_json, dimension "
                        "FROM vector_records"
                    )
                )
            return list(
                conn.execute(
                    "SELECT chunk_id, source_id, task_id, embedding_json, metadata_json, dimension "
                    "FROM vector_records WHERE task_id = ?",
                    (task_id,),
                )
            )

    def _validate_batch(self, records: list[VectorRecord]) -> int:
        dimension = len(records[0].embedding)
        if dimension <= 0:
            raise ValueError("record embedding 不能为空")
        for rec in records:
            if not rec.embedding:
                raise ValueError("record embedding 不能为空")
            if len(rec.embedding) != dimension:
                raise ValueError(
                    f"record embedding 维度不一致：期望 {dimension}，实际 {len(rec.embedding)}"
                )
        return dimension

    @staticmethod
    def _load_metadata(raw: str) -> dict[str, Any]:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        num = sum(x * y for x, y in zip(a, b, strict=False))
        na = sqrt(sum(x * x for x in a))
        nb = sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(num / (na * nb))
