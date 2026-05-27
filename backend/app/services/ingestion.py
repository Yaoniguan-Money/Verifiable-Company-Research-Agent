"""Ingest source text into evidence chunks."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import EvidenceChunk
from app.repositories import ResearchArtifactRepository
from app.schemas.common import SOURCE_CREDIBILITY_SCORE_METADATA_KEY, SOURCE_METADATA_KEY
from app.services.chunking import ChunkingService
from app.services.content_enrichment import ContentEnrichmentPipeline
from app.services.pdf_ingestion import enrich_pdf_raw_content


class IngestionService:
    """将指定 Source 的原文切分并写入 ``evidence_chunks``（先删后插，仅本 ``source_id``+``task_id``）。

    **Session 与事务**：
    - 会**修改**调用方传入的 ``db`` session（``delete`` / ``add`` / ``flush`` / ``refresh``），**不**执行 ``commit``。
    - **事务边界由调用方负责**（在适当时机 ``commit`` 或 ``rollback``）。
    - 本服务不做 embedding、vector store、retrieval；``embedding_id`` 仅可保留占位符。
    """

    def __init__(
        self,
        db: Session,
        chunker: ChunkingService | None = None,
        enrichment_pipeline: ContentEnrichmentPipeline | None = None,
    ) -> None:
        self.db = db
        self.artifacts = ResearchArtifactRepository(db)
        self._chunker = chunker or ChunkingService()
        self._enrichment = enrichment_pipeline

    def ingest_chunks_for_source(
        self,
        task_id: str,
        source_id: str,
        *,
        chunk_size: int = 140,
        chunk_overlap: int = 0,
    ) -> list[EvidenceChunk]:
        """对单个 Source 切分并写入多行；**不 commit**，仅 ``flush`` 以使主键等可用。

        会修改同一 ``db`` session；调用方在全部需要的操作结束后统一 ``commit``。
        本方法不创建真实向量、不访问向量库、不执行检索；当前阶段无 embedding/vector store/retrieval。
        """

        source = self.artifacts.get_source(source_id)
        if source is None:
            raise ValueError("资料来源不存在，无法入库切片")
        if source.task_id != task_id:
            raise ValueError("资料来源与任务 ID 不一致，已拒绝写入以避免串任务污染")

        self.artifacts.delete_chunks_for_source(task_id=task_id, source_id=source_id)

        enriched = self._enrich_source_content(source)
        parts = self._chunker.split(
            enriched,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            source_title=source.title,
            source_url=source.url,
            source_type=str(source.source_type),
            retrieved_at=source.retrieved_at,
        )
        created: list[EvidenceChunk] = []
        for part in parts:
            metadata = {
                **part.metadata,
                SOURCE_CREDIBILITY_SCORE_METADATA_KEY: source.credibility_score,
                SOURCE_METADATA_KEY: source.source_metadata or {},
            }
            row = EvidenceChunk(
                source_id=source_id,
                task_id=task_id,
                chunk_index=part.chunk_index,
                text=part.text,
                chunk_metadata=metadata,
                embedding_id=f"mock-emb-{source_id[:8]}-{part.chunk_index}",
            )
            self.artifacts.add_chunk(row)
            created.append(row)
        # 单 source 内一次 flush，由工作流在全部 source 处理完后统一 commit。
        self.db.flush()
        for row in created:
            self.db.refresh(row)
        return created

    def _enrich_source_content(self, source) -> str:
        """Run content enrichment pipeline if available, otherwise fall back to legacy."""
        if self._enrichment is not None:
            from app.schemas.source import SourceRead
            source_read = SourceRead.model_validate(source)
            enriched = self._enrichment.enrich(source_read, question="")
            return enriched.raw
        return enrich_pdf_raw_content(source.raw_content, source.source_metadata)
