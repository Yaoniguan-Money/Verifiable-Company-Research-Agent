"""Text chunking service with pluggable strategies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config import get_settings
from app.services.chunking_strategy.base import ChunkMetadata, ChunkingPart, ChunkingStrategy
from app.services.chunking_strategy.fixed_window import FixedWindowChunker
from app.services.chunking_strategy.recursive import RecursiveTextSplitter
from app.services.chunking_strategy.section_aware import SectionAwareChunker


class ChunkingService:
    """Pluggable text chunking via ``ChunkingStrategy``.

    Strategy is selected via ``CHUNKING_STRATEGY`` config. Falls back to
    ``FixedWindowChunker`` when no strategy is explicitly provided.
    """

    def __init__(self, strategy: ChunkingStrategy | None = None) -> None:
        self._strategy = strategy

    def split(
        self,
        raw_content: str,
        *,
        chunk_size: int,
        chunk_overlap: int,
        source_title: str = "",
        source_url: str | None = None,
        source_type: str = "",
        retrieved_at: datetime | None = None,
    ) -> list[ChunkingPart]:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")

        strategy = self._strategy or self._default_strategy(chunk_size, chunk_overlap)
        metadata = ChunkMetadata(
            source_title=source_title,
            source_url=source_url,
            source_type=str(source_type),
            retrieved_at=retrieved_at,
        )
        return strategy.split(raw_content or "", metadata)

    def _default_strategy(self, chunk_size: int, chunk_overlap: int) -> ChunkingStrategy:
        settings = get_settings()
        name = settings.chunking_strategy
        if name == "section_aware":
            return SectionAwareChunker(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                min_chunk_size=settings.section_min_chunk_size,
            )
        if name == "recursive":
            return RecursiveTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        return FixedWindowChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
