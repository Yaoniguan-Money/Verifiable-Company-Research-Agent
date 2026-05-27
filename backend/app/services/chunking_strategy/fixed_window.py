from __future__ import annotations

from typing import Any

from app.services.chunking_strategy.base import (
    ChunkingPart,
    ChunkingStrategy,
    ChunkMetadata,
)


class FixedWindowChunker(ChunkingStrategy):
    """Fixed-character-window chunking (preserves existing behaviour)."""

    def __init__(self, *, chunk_size: int, chunk_overlap: int) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    @property
    def strategy_name(self) -> str:
        return "fixed_window"

    def split(self, text: str, metadata: ChunkMetadata) -> list[ChunkingPart]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        n = len(cleaned)
        base_meta: dict[str, Any] = {
            "source_title": metadata.source_title,
            "source_url": metadata.source_url,
            "source_type": str(metadata.source_type),
            "retrieved_at": metadata.retrieved_at.isoformat() if metadata.retrieved_at else None,
            "chunk_size": self._chunk_size,
            "chunk_overlap": self._chunk_overlap,
            "strategy": self.strategy_name,
        }
        out: list[ChunkingPart] = []
        idx = 0
        start = 0
        step = max(1, self._chunk_size - self._chunk_overlap)
        while start < n:
            end = min(start + self._chunk_size, n)
            piece = cleaned[start:end]
            piece_meta = {**base_meta, "char_start": start, "char_end": end}
            out.append(ChunkingPart(chunk_index=idx, text=piece, metadata=piece_meta))
            idx += 1
            if end >= n:
                break
            start += step
        return out
