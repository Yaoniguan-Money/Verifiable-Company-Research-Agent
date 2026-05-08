r"""RAG smoke script: ingestion -> embedding -> vector_store -> retrieval -> grounding.

Run from the project root in PowerShell:
  $env:PYTHONPATH = "backend"
  .\\.venv\\Scripts\\python.exe scripts\\verify_rag_smoke.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/dev.db")
os.environ.setdefault("APP_ENV", "dev")

from app.core.config import get_settings  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.db.init_db import get_default_user, init_db  # noqa: E402
from app.db.models import EvidenceChunk, ResearchTask, Source  # noqa: E402
from app.db.models.source import SourceType  # noqa: E402
from app.providers.embedding.mock_provider import MockEmbeddingProvider  # noqa: E402
from app.services.embedding import EmbeddingService  # noqa: E402
from app.services.ingestion import IngestionService  # noqa: E402
from app.services.report_grounding import ReportGroundingService  # noqa: E402
from app.services.retrieval import RetrievalService  # noqa: E402
from app.vectorstores import InMemoryVectorStore, VectorRecord  # noqa: E402


def main() -> None:
    get_settings.cache_clear()
    db_session.reset_engine()
    init_db()

    db = db_session.SessionLocal()
    try:
        user = get_default_user(db)
        task = ResearchTask(
            user_id=user.id,
            company_name="RAG Verification Company",
            question="Show grounded evidence for R&D investment and operating risk",
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        src = Source(
            task_id=task.id,
            title="RAG Verification Notice",
            url="https://example.com/rag/notice",
            source_type=SourceType.ANNOUNCEMENT,
            published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            retrieved_at=datetime.now(timezone.utc),
            raw_content=(
                "Public disclosure shows sustained growth in R&D investment. "
                "It also warns that raw material volatility and supplier uncertainty may "
                "affect delivery cadence."
            ),
        )
        db.add(src)
        db.commit()
        db.refresh(src)

        chunks = IngestionService(db).ingest_chunks_for_source(
            task.id, src.id, chunk_size=36, chunk_overlap=0
        )
        db.commit()
        assert chunks, "ingestion should produce at least one chunk"

        provider = MockEmbeddingProvider(dimension=8)
        emb_results = EmbeddingService(db, provider).embed_and_persist_ids(chunks)
        db.commit()
        assert emb_results, "embedding results should not be empty"

        store = InMemoryVectorStore()
        records = [
            VectorRecord(
                chunk_id=item.chunk_id,
                source_id=next(ch.source_id for ch in chunks if ch.id == item.chunk_id),
                task_id=task.id,
                embedding=item.vector,
                metadata={"embedding_id": item.embedding_id},
            )
            for item in emb_results
        ]
        added = store.add_embeddings(records)
        assert added == len(records), "vector-store insert count should match"

        retrieved = RetrievalService(db).retrieve_for_task(
            task_id=task.id,
            query="R&D investment and supply chain risk",
            top_k=5,
            embedding_provider=provider,
            vector_store=store,
        )
        assert retrieved, "retrieval should return at least one evidence item"

        grounding = ReportGroundingService().build_grounded_section(
            query="R&D investment and supply chain risk",
            evidences=retrieved,
            max_items=3,
        )
        assert grounding.citations, "grounding should produce citations when evidence exists"
        for cit in grounding.citations:
            assert db.get(EvidenceChunk, cit.chunk_id) is not None
            assert db.get(Source, cit.source_id) is not None

        no_evidence = RetrievalService(db).retrieve_for_task(
            task_id=task.id,
            query="totally random no-hit phrase XYZ",
            top_k=0,
            embedding_provider=provider,
            vector_store=store,
        )
        assert no_evidence == []
        no_sec = ReportGroundingService().build_grounded_section(
            query="totally random no-hit phrase XYZ",
            evidences=no_evidence,
        )
        no_evidence_text = no_sec.content.lower()
        # 断言兼容中英文，避免把业务文案硬改回英文。
        assert any(
            keyword in no_evidence_text
            for keyword in ("证据不足", "未找到", "无证据", "evidence")
        )
        assert no_sec.citations == []

        print(
            "OK RAG:",
            f"task_id={task.id}",
            f"chunks={len(chunks)}",
            f"citations={len(grounding.citations)}",
        )
        print("OK TRACEABILITY: citations can resolve back to source_id and chunk_id")
        print("OK NO_EVIDENCE: empty evidence path does not invent citations")
    finally:
        db.close()


if __name__ == "__main__":
    main()
