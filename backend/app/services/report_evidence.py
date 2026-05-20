from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import EvidenceChunk, ResearchTask
from app.providers.embedding import EmbeddingProvider
from app.providers.factory import ProviderFactory
from app.repositories import ResearchArtifactRepository
from app.schemas.chunk import Citation
from app.schemas.common import (
    SOURCE_CREDIBILITY_SCORE_METADATA_KEY,
    SOURCE_METADATA_KEY,
    SourceAuthority,
    SourceLayer,
    authority_label,
    is_official_body_layer,
    source_layer_from_metadata,
    source_layer_priority,
)
from app.schemas.retrieval import RetrievedEvidence
from app.services.embedding import ChunkEmbeddingResult, EmbeddingService
from app.services.report_grounding import ReportGroundingService
from app.services.retrieval import RetrievalService
from app.vectorstores import VectorRecord, VectorStore


class ReportEvidenceService:
    """Build report evidence snippets and citation lists.

    Embedding, retrieval, official-body evidence inclusion, and citation sorting stay here
    so graph nodes can reuse one rule boundary instead of duplicating ranking logic.
    """

    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        self.artifacts = ResearchArtifactRepository(db)
        providers = ProviderFactory(self.settings)
        self.embedding_provider = embedding_provider or providers.create_embedding_provider()
        self.vector_store = vector_store or providers.create_vector_store()

    def build_report_evidence(self, task: ResearchTask) -> tuple[str, list[Citation]]:
        grounded_content, grounded_citations = self.build_grounded_section(task)
        return grounded_content, self.merge_with_fact_citations(task.id, grounded_citations)

    def build_grounded_section(self, task: ResearchTask) -> tuple[str, list[Citation]]:
        chunk_rows = self.artifacts.list_chunks(task.id)
        grounding = ReportGroundingService()
        if not chunk_rows:
            section = grounding.build_grounded_section(query=task.question, evidences=[])
            return section.content, section.citations

        emb_results = self.embed_and_index_chunks(task.id, chunk_rows)
        evidences = self.retrieve_evidence_for_task(
            task=task,
            indexed_chunk_count=len(emb_results),
        )
        return self.build_grounded_section_from_evidence(task=task, evidences=evidences)

    def embed_and_index_chunks(
        self,
        task_id: str,
        chunk_rows: list[EvidenceChunk] | None = None,
    ) -> list[ChunkEmbeddingResult]:
        chunks = chunk_rows if chunk_rows is not None else self.artifacts.list_chunks(task_id)
        if not chunks:
            return []

        emb_results = EmbeddingService(
            self.db,
            self.embedding_provider,
        ).embed_and_persist_ids(chunks)
        self.vector_store.delete_task(task_id)
        chunk_source_map = {item.id: item.source_id for item in chunks}
        self.vector_store.add_embeddings(
            [
                VectorRecord(
                    chunk_id=item.chunk_id,
                    source_id=chunk_source_map[item.chunk_id],
                    task_id=task_id,
                    embedding=item.vector,
                    metadata={"embedding_id": item.embedding_id, "dimension": item.dimension},
                )
                for item in emb_results
            ]
        )
        return emb_results

    def retrieve_evidence_for_task(
        self,
        *,
        task: ResearchTask,
        indexed_chunk_count: int | None = None,
    ) -> list[RetrievedEvidence]:
        top_k_ceiling = indexed_chunk_count
        if top_k_ceiling is None:
            top_k_ceiling = len(self.artifacts.list_chunks(task.id))
        if top_k_ceiling <= 0:
            return self._include_official_body_evidence(task.id, [])

        evidences = RetrievalService(self.db).retrieve_for_task(
            task_id=task.id,
            query=task.question,
            top_k=min(self.settings.retrieval_top_k, top_k_ceiling),
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
        )
        return self._include_official_body_evidence(task.id, evidences)

    def build_grounded_section_from_evidence(
        self,
        *,
        task: ResearchTask,
        evidences: list[RetrievedEvidence],
    ) -> tuple[str, list[Citation]]:
        section = ReportGroundingService().build_grounded_section(
            query=task.question,
            evidences=evidences,
            max_items=3,
        )
        return section.content, section.citations

    def merge_with_fact_citations(
        self,
        task_id: str,
        grounded_citations: list[Citation],
    ) -> list[Citation]:
        fact_citations = self._build_fact_citations(task_id)
        return self._sort_citations_by_source_quality(
            task_id,
            self._merge_citations(grounded_citations, fact_citations),
        )

    def build_source_quality_summary(self, task_id: str) -> str:
        sources = self.artifacts.list_sources(task_id)
        counts = {
            SourceAuthority.HIGH.value: 0,
            SourceAuthority.MEDIUM.value: 0,
            SourceAuthority.LOW.value: 0,
            SourceAuthority.UNKNOWN.value: 0,
        }
        layer_counts = {
            "official_body": 0,
            SourceLayer.OFFICIAL_ENTRY_PAGE.value: 0,
            SourceLayer.THIRD_PARTY_BACKGROUND.value: 0,
            SourceAuthority.LOW.value: 0,
        }
        for source in sources:
            authority = authority_label(source.credibility_score)
            counts[authority.value] += 1
            layer = source_layer_from_metadata(source.source_metadata)
            if is_official_body_layer(layer):
                layer_counts["official_body"] += 1
            elif layer == SourceLayer.OFFICIAL_ENTRY_PAGE:
                layer_counts[SourceLayer.OFFICIAL_ENTRY_PAGE.value] += 1
            else:
                layer_counts[SourceLayer.THIRD_PARTY_BACKGROUND.value] += 1
            if authority == SourceAuthority.LOW:
                layer_counts[SourceAuthority.LOW.value] += 1
        has_authoritative = counts[SourceAuthority.HIGH.value] > 0
        has_official_body = layer_counts["official_body"] > 0
        if has_official_body:
            evidence_strength = "较高"
            limitation = "已经拿到官方披露正文或官方 PDF，可以支撑后续事实核验。"
        elif has_authoritative:
            evidence_strength = "中等"
            limitation = "目前只有官方入口，缺少具体披露正文；财务和经营结论仍需补证。"
        else:
            evidence_strength = "偏低"
            limitation = "高权威来源不足，现有材料更适合作线索，不适合作确定结论。"
        return "\n".join(
            [
                "## 来源质量摘要",
                f"- 本次证据强度：{evidence_strength}。",
                f"- 官方/监管/交易所正文：{layer_counts['official_body']} 条。",
                f"- 官方入口但不是正文：{layer_counts[SourceLayer.OFFICIAL_ENTRY_PAGE.value]} 条。",
                f"- 第三方背景材料：{layer_counts[SourceLayer.THIRD_PARTY_BACKGROUND.value]} 条。",
                f"- 低可信来源：{layer_counts[SourceAuthority.LOW.value]} 条。",
                f"- 解读：{limitation}",
            ]
        )

    def _build_fact_citations(self, task_id: str) -> list[Citation]:
        facts = self.artifacts.list_facts(task_id)
        source_map = self.artifacts.source_map(task_id)
        chunk_map = self.artifacts.chunk_map(task_id)

        citations: list[Citation] = []
        seen: set[tuple[str, str]] = set()
        for fact in facts:
            key = (fact.source_id, fact.chunk_id)
            if key in seen:
                continue
            source = source_map.get(fact.source_id)
            chunk = chunk_map.get(fact.chunk_id)
            if source is None or chunk is None:
                continue
            citations.append(
                Citation(
                    source_id=source.id,
                    chunk_id=chunk.id,
                    url=source.url,
                    title=source.title,
                    retrieved_at=source.retrieved_at,
                )
            )
            seen.add(key)
        return citations

    def _include_official_body_evidence(
        self,
        task_id: str,
        evidences: list[RetrievedEvidence],
    ) -> list[RetrievedEvidence]:
        source_map = self.artifacts.source_map(task_id)
        seen_chunks = {item.chunk_id for item in evidences}
        out = list(evidences)
        added_sources: set[str] = set()
        for chunk in self.artifacts.list_chunks(task_id):
            if chunk.id in seen_chunks or chunk.source_id in added_sources:
                continue
            source = source_map.get(chunk.source_id)
            if source is None:
                continue
            if not is_official_body_layer(source_layer_from_metadata(source.source_metadata)):
                continue
            out.append(
                RetrievedEvidence(
                    chunk_id=chunk.id,
                    source_id=source.id,
                    task_id=task_id,
                    text=chunk.text,
                    score=0.01,
                    source_title=source.title,
                    source_url=source.url,
                    source_type=str(source.source_type),
                    retrieved_at=source.retrieved_at,
                    metadata={
                        **(chunk.chunk_metadata or {}),
                        SOURCE_CREDIBILITY_SCORE_METADATA_KEY: source.credibility_score,
                        SOURCE_METADATA_KEY: source.source_metadata or {},
                    },
                )
            )
            added_sources.add(source.id)
        return out

    def _merge_citations(
        self,
        primary: list[Citation],
        secondary: list[Citation],
    ) -> list[Citation]:
        out: list[Citation] = []
        seen: set[tuple[str, str]] = set()
        for item in [*primary, *secondary]:
            key = (item.source_id, item.chunk_id)
            if key in seen:
                continue
            out.append(item)
            seen.add(key)
        return out

    def _sort_citations_by_source_quality(
        self,
        task_id: str,
        citations: list[Citation],
    ) -> list[Citation]:
        source_map = self.artifacts.source_map(task_id)
        return sorted(
            citations,
            key=lambda item: (
                source_layer_priority(
                    source_layer_from_metadata(
                        source_map.get(item.source_id).source_metadata
                        if source_map.get(item.source_id) is not None
                        else None
                    )
                ),
                source_map.get(item.source_id).credibility_score
                if source_map.get(item.source_id) is not None
                and source_map.get(item.source_id).credibility_score is not None
                else 0,
                item.retrieved_at,
            ),
            reverse=True,
        )
