from __future__ import annotations

from app.providers.search.base import SearchProvider
from app.schemas.common import SOURCE_LAYER_METADATA_KEY, source_layer_priority
from app.schemas.source import SourceCreate


class HybridPublicSearchProvider(SearchProvider):
    """组合多个公开资料 provider。

    默认先取高可信官方披露，再补充搜索引擎返回的公开网页；下游 verification 仍负责判断证据是否足够。
    """

    def __init__(self, providers: list[SearchProvider]) -> None:
        self.providers = providers

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        out: list[SourceCreate] = []
        seen_urls: set[str] = set()
        errors: list[str] = []
        for provider in self.providers:
            try:
                sources = provider.search(company_name, question)
            except Exception as exc:
                errors.append(f"{provider.__class__.__name__}: {exc}")
                continue
            for source in sources:
                url_key = _source_dedupe_key(source)
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                out.append(source)
        if not out:
            raise ValueError("Hybrid public search returned no usable sources; " + "; ".join(errors))
        return sorted(
            out,
            key=lambda item: (
                source_layer_priority((item.source_metadata or {}).get(SOURCE_LAYER_METADATA_KEY)),
                item.credibility_score or 0,
            ),
            reverse=True,
        )


def _source_dedupe_key(source: SourceCreate) -> str:
    url = (source.url or "").strip().lower()
    if url:
        return url
    # 无 URL 的本地资料只按标题会误杀，带上正文长度降低误去重概率。
    return f"{source.title.strip().lower()}:{len(source.raw_content or '')}"
