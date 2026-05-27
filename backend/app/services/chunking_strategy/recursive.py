from __future__ import annotations

from typing import Any

from app.services.chunking_strategy.base import (
    ChunkingPart,
    ChunkingStrategy,
    ChunkMetadata,
)

_DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "；", "，", " "]


class RecursiveTextSplitter(ChunkingStrategy):
    """Recursively split at the most semantic boundary available.

    Tries separators in priority order. Only falls back to character-level
    splitting when no semantic boundary is found.
    """

    def __init__(
        self,
        *,
        chunk_size: int,
        chunk_overlap: int,
        separators: list[str] | None = None,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._separators = separators or _DEFAULT_SEPARATORS

    @property
    def strategy_name(self) -> str:
        return "recursive"

    def split(self, text: str, metadata: ChunkMetadata) -> list[ChunkingPart]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []
        base_meta = self._base_meta(metadata)
        chunks = self._split_recursive(cleaned, self._separators)
        return self._parts_from_chunks(cleaned, chunks, base_meta)

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        result: list[str] = []
        if len(text) <= self._chunk_size:
            return [text] if text.strip() else []

        sep = separators[0] if separators else ""
        if not sep:
            return self._split_fixed(text)

        splits = text.split(sep)
        current = ""
        for part in splits:
            if not current:
                current = part
            elif len(current) + len(sep) + len(part) <= self._chunk_size:
                current += sep + part
            else:
                if len(current) > self._chunk_size:
                    result.extend(
                        self._split_recursive(current, separators[1:])
                        if len(separators) > 1
                        else self._split_fixed(current)
                    )
                else:
                    result.append(current)
                current = part
        if current:
            if len(current) > self._chunk_size:
                result.extend(
                    self._split_recursive(current, separators[1:])
                    if len(separators) > 1
                    else self._split_fixed(current)
                )
            else:
                result.append(current)
        return result

    def _split_fixed(self, text: str) -> list[str]:
        n = len(text)
        if n <= self._chunk_size:
            return [text]
        chunks: list[str] = []
        step = max(1, self._chunk_size - self._chunk_overlap)
        for start in range(0, n, step):
            chunks.append(text[start : start + self._chunk_size])
        return chunks

    def _parts_from_chunks(
        self,
        source_text: str,
        chunks: list[str],
        base_meta: dict[str, Any],
    ) -> list[ChunkingPart]:
        parts: list[ChunkingPart] = []
        cursor = 0
        for index, chunk in enumerate(chunks):
            # 递归分块可能带重叠，向前回看 overlap，才能定位到真实原文位置。
            search_from = max(0, cursor - self._chunk_overlap)
            start = source_text.find(chunk, search_from)
            if start < 0:
                start = cursor
            end = start + len(chunk)
            parts.append(
                ChunkingPart(
                    chunk_index=index,
                    text=chunk,
                    metadata={**base_meta, "char_start": start, "char_end": end},
                )
            )
            cursor = end
        return parts

    def _base_meta(self, metadata: ChunkMetadata) -> dict[str, Any]:
        return {
            "source_title": metadata.source_title,
            "source_url": metadata.source_url,
            "source_type": str(metadata.source_type),
            "retrieved_at": metadata.retrieved_at.isoformat() if metadata.retrieved_at else None,
            "chunk_size": self._chunk_size,
            "chunk_overlap": self._chunk_overlap,
            "strategy": self.strategy_name,
        }
