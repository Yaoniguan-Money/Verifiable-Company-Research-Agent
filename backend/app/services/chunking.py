"""Deterministic text chunking without LLM, embedding, or vector-store work."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ChunkingPart:
    """单段切分结果（内存对象，不直接等同 ORM 行）。"""

    chunk_index: int
    text: str
    metadata: dict[str, Any]


class ChunkingService:
    """按固定字符窗口切分；确定性、可单测。"""

    def split(
        self,
        raw_content: str,
        *,
        chunk_size: int = 140,
        chunk_overlap: int = 0,
        source_title: str = "",
        source_url: str | None = None,
        source_type: str = "",
        retrieved_at: datetime | None = None,
    ) -> list[ChunkingPart]:
        """将 ``raw_content`` 切成多段。

        空串或全空白：返回空列表。``chunk_index`` 自 0 起递增。
        """
        if chunk_size < 1:
            raise ValueError("chunk_size 须 >= 1")
        if chunk_overlap < 0:
            raise ValueError("chunk_overlap 须 >= 0")
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 须小于 chunk_size，否则无法前进")

        text = (raw_content or "").strip()
        if not text:
            return []

        n = len(text)
        base_meta: dict[str, Any] = {
            "source_title": source_title,
            "source_url": source_url,
            "source_type": str(source_type),
            "retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "strategy": "char_window",
        }
        out: list[ChunkingPart] = []
        idx = 0
        start = 0
        step = max(1, chunk_size - chunk_overlap)
        while start < n:
            end = min(start + chunk_size, n)
            piece = text[start:end]
            meta = {
                **base_meta,
                "char_start": start,
                "char_end": end,
            }
            out.append(ChunkingPart(chunk_index=idx, text=piece, metadata=meta))
            idx += 1
            if end >= n:
                break
            start += step
        return out
