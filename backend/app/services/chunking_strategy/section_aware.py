from __future__ import annotations

import re
from typing import Any

from app.services.chunking_strategy.base import (
    ChunkingPart,
    ChunkingStrategy,
    ChunkMetadata,
)

_SECTION_MARKER_RE = re.compile(r"\n\n<!-- SECTION: (.+?) -->\n")


class SectionAwareChunker(ChunkingStrategy):
    """Split at section boundary markers inserted by ``SectionAnnotator``.

    Sections shorter than ``min_chunk_size`` are merged with neighbours.
    Sections longer than ``chunk_size`` are recursively split at semantic
    boundaries (falling back to ``RecursiveTextSplitter`` behaviour).
    """

    def __init__(
        self,
        *,
        chunk_size: int,
        chunk_overlap: int,
        min_chunk_size: int = 400,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be < chunk_size")
        if min_chunk_size < 1:
            raise ValueError("min_chunk_size must be >= 1")
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._min_chunk_size = min_chunk_size

    @property
    def strategy_name(self) -> str:
        return "section_aware"

    def split(self, text: str, metadata: ChunkMetadata) -> list[ChunkingPart]:
        cleaned = (text or "").strip()
        if not cleaned:
            return []

        sections = self._parse_sections(cleaned)
        merged = self._merge_short_sections(sections)
        parts: list[ChunkingPart] = []
        idx = 0
        base_meta = self._base_meta(metadata)

        for section_title, section_text in merged:
            if len(section_text) <= self._chunk_size:
                parts.append(ChunkingPart(
                    chunk_index=idx,
                    text=section_text,
                    metadata={**base_meta, "section": section_title},
                ))
                idx += 1
            else:
                for sub in self._split_long_section(section_text):
                    parts.append(ChunkingPart(
                        chunk_index=idx,
                        text=sub,
                        metadata={**base_meta, "section": section_title},
                    ))
                    idx += 1
        return parts

    def _parse_sections(self, text: str) -> list[tuple[str, str]]:
        markers = list(_SECTION_MARKER_RE.finditer(text))
        if not markers:
            return [("正文", text)]

        sections: list[tuple[str, str]] = []
        preamble = text[: markers[0].start()].strip()
        if preamble:
            sections.append(("正文", preamble))

        for index, marker in enumerate(markers):
            title = marker.group(1).strip() or "正文"
            start = marker.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            content = text[start:end].strip()
            if content:
                sections.append((title, content))
        return sections

    def _merge_short_sections(self, sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
        merged: list[tuple[str, str]] = []
        buffer_title = ""
        buffer_text = ""
        for title, text in sections:
            if len(text) < self._min_chunk_size:
                if buffer_text:
                    buffer_text += "\n\n" + text
                else:
                    buffer_title = title
                    buffer_text = text
            else:
                if buffer_text:
                    buffer_text += "\n\n" + text
                    merged.append((buffer_title or title, buffer_text))
                    buffer_title = ""
                    buffer_text = ""
                else:
                    merged.append((title, text))
        if buffer_text:
            merged.append((buffer_title, buffer_text))
        return merged

    def _split_long_section(self, text: str) -> list[str]:
        separators = ["\n\n", "\n", "。", "；", "，", " "]
        chunks: list[str] = []
        remaining = text
        while len(remaining) > self._chunk_size:
            split_at = self._find_best_split(remaining, separators)
            if split_at <= 0:
                split_at = self._chunk_size
            chunks.append(remaining[:split_at].strip())
            # 保留少量重叠，避免跨边界的句子在检索时被硬切断。
            overlap_start = max(0, split_at - self._chunk_overlap)
            remaining = remaining[overlap_start:]
        if remaining.strip():
            chunks.append(remaining.strip())
        return chunks

    def _find_best_split(self, text: str, separators: list[str]) -> int:
        for sep in separators:
            search_start = max(0, self._chunk_size - 200)
            pos = text.rfind(sep, search_start, self._chunk_size + 200)
            if pos > 0:
                return pos + len(sep)
        return self._chunk_size

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
