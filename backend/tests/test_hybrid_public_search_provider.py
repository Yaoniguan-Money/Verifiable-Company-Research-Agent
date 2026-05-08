from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.providers.search.base import SearchProvider
from app.providers.search.hybrid_public import HybridPublicSearchProvider
from app.schemas.common import SourceType
from app.schemas.source import SourceCreate


class FakeProvider(SearchProvider):
    def __init__(self, sources: list[SourceCreate] | None = None, error: Exception | None = None) -> None:
        self.sources = sources or []
        self.error = error

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        if self.error:
            raise self.error
        return self.sources


def _source(title: str, url: str, score: float) -> SourceCreate:
    return SourceCreate(
        task_id="task",
        title=title,
        url=url,
        source_type=SourceType.OTHER,
        retrieved_at=datetime.now(timezone.utc),
        raw_content="公开资料正文",
        credibility_score=score,
    )


def test_hybrid_public_provider_dedupes_and_sorts_sources() -> None:
    provider = HybridPublicSearchProvider(
        [
            FakeProvider([_source("官方年报", "https://example.com/report.pdf", 0.95)]),
            FakeProvider(
                [
                    _source("重复来源", "https://example.com/report.pdf", 0.72),
                    _source("新闻补充", "https://news.example.com/item", 0.72),
                ]
            ),
        ]
    )

    sources = provider.search("样例股份", "研发")

    assert [item.title for item in sources] == ["官方年报", "新闻补充"]


def test_hybrid_public_provider_raises_only_when_all_sources_fail() -> None:
    provider = HybridPublicSearchProvider([FakeProvider(error=ValueError("boom"))])

    with pytest.raises(ValueError, match="no usable sources"):
        provider.search("样例股份", "研发")
