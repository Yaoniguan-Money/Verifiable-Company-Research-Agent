"""Recursive chunking edge cases."""

from __future__ import annotations

import pytest
from app.services.chunking_strategy.base import ChunkMetadata
from app.services.chunking_strategy.recursive import RecursiveTextSplitter


def test_recursive_splitter_validates_overlap() -> None:
    with pytest.raises(ValueError, match="chunk_overlap must be >= 0"):
        RecursiveTextSplitter(chunk_size=10, chunk_overlap=-1)

    with pytest.raises(ValueError, match="chunk_overlap must be < chunk_size"):
        RecursiveTextSplitter(chunk_size=10, chunk_overlap=10)


def test_recursive_splitter_reports_original_character_offsets() -> None:
    text = "第一段内容。\n\n第二段内容更长。\n\n第三段。"
    splitter = RecursiveTextSplitter(chunk_size=12, chunk_overlap=0)

    parts = splitter.split(text, ChunkMetadata(source_title="测试"))

    assert [part.text for part in parts] == ["第一段内容。", "第二段内容更长。", "第三段。"]
    assert [
        (part.metadata["char_start"], part.metadata["char_end"])
        for part in parts
    ] == [(0, 6), (8, 16), (18, 22)]


def test_recursive_splitter_offsets_handle_fixed_overlap() -> None:
    text = "abcdefghij"
    splitter = RecursiveTextSplitter(chunk_size=4, chunk_overlap=2, separators=[])

    parts = splitter.split(text, ChunkMetadata())

    assert [part.text for part in parts] == ["abcd", "cdef", "efgh", "ghij", "ij"]
    assert [
        (part.metadata["char_start"], part.metadata["char_end"])
        for part in parts
    ] == [(0, 4), (2, 6), (4, 8), (6, 10), (8, 10)]
