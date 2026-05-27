"""搜索结果 Redis 缓存装饰器。"""

from __future__ import annotations

from app.infra.redis_cache import RedisCache
from app.providers.search.base import SearchProvider
from app.schemas.source import SourceCreate


class CachedSearchProvider(SearchProvider):
    def __init__(
        self,
        inner: SearchProvider,
        *,
        cache: RedisCache,
        ttl_seconds: int,
    ) -> None:
        self.inner = inner
        self.cache = cache
        self.ttl_seconds = ttl_seconds

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        if not self.cache.enabled:
            return self.inner.search(company_name, question)

        key = self.cache.search_cache_key(company_name, question)
        cached = self.cache.get_json(key)
        if isinstance(cached, list):
            return [SourceCreate.model_validate(item) for item in cached]

        sources = self.inner.search(company_name, question)
        self.cache.set_json(
            key,
            [item.model_dump(mode="json") for item in sources],
            ttl_seconds=self.ttl_seconds,
        )
        return sources
