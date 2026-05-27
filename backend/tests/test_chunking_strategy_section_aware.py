"""Section-aware chunking edge cases."""

from __future__ import annotations

import pytest
from app.services.chunking_strategy.base import ChunkMetadata
from app.services.chunking_strategy.section_aware import SectionAwareChunker


def test_section_aware_chunker_validates_sizes() -> None:
    with pytest.raises(ValueError, match="chunk_size must be >= 1"):
        SectionAwareChunker(chunk_size=0, chunk_overlap=0)

    with pytest.raises(ValueError, match="chunk_overlap must be < chunk_size"):
        SectionAwareChunker(chunk_size=10, chunk_overlap=10)

    with pytest.raises(ValueError, match="min_chunk_size must be >= 1"):
        SectionAwareChunker(chunk_size=10, chunk_overlap=0, min_chunk_size=0)


def test_section_markers_are_attached_to_following_content() -> None:
    text = (
        "前言说明"
        "\n\n<!-- SECTION: 研发投入 -->\n研发费用增长。"
        "\n\n<!-- SECTION: 营收 -->\n营业收入增长。"
    )
    chunker = SectionAwareChunker(chunk_size=100, chunk_overlap=0, min_chunk_size=1)

    parts = chunker.split(text, ChunkMetadata())

    assert [(part.metadata["section"], part.text) for part in parts] == [
        ("正文", "前言说明"),
        ("研发投入", "研发费用增长。"),
        ("营收", "营业收入增长。"),
    ]
