"""Redis 缓存：搜索结果 TTL 缓存与速率限制计数。

未配置 ``REDIS_URL`` 或连接失败时全部降级为 no-op，保证本地无 Redis 也能跑全部测试。
"""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisCache:
    """轻量 Redis 封装；连接失败时不抛错，便于本地无 Redis 开发。"""

    def __init__(self, redis_url: str | None) -> None:
        self._client: Any | None = None
        if not redis_url:
            return
        try:
            import redis  # type: ignore[import-untyped]

            self._client = redis.from_url(redis_url, decode_responses=True)
            self._client.ping()
            logger.info("Redis 已连接")
        except Exception as exc:  # noqa: BLE001 — 这里就是要兜底所有底层异常并降级。
            logger.warning("Redis 不可用，缓存已禁用: %s", exc)
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def get_json(self, key: str) -> Any | None:
        if self._client is None:
            return None
        raw = self._client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        if self._client is None:
            return
        self._client.setex(key, ttl_seconds, json.dumps(value, ensure_ascii=False))

    def incr(self, key: str, *, ttl_seconds: int | None = None) -> int:
        if self._client is None:
            return 0
        count = int(self._client.incr(key))
        if ttl_seconds and count == 1:
            self._client.expire(key, ttl_seconds)
        return count

    @staticmethod
    def search_cache_key(company: str, question: str) -> str:
        """搜索结果的 cache key：仅做命中检索用途，不涉及安全场景，MD5 足够稳定。"""
        digest = hashlib.md5(f"{company}:{question}".encode()).hexdigest()
        return f"search:{digest}"


@lru_cache
def get_redis_cache() -> RedisCache:
    settings = get_settings()
    return RedisCache(settings.redis_url)
