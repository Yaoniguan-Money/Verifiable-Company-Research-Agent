from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from app.core.config import get_settings
from app.services.content_enrichment.base import ContentEnricher, EnrichedContent

if TYPE_CHECKING:
    from app.schemas.source import SourceRead

logger = logging.getLogger(__name__)


class PDFCache(ContentEnricher):
    """Download PDF from source URL and cache locally.

    Uses a content-hash-based cache directory. On cache hit, sets
    ``local_pdf_path`` in content metadata without re-downloading.
    """

    def __init__(
        self,
        *,
        cache_dir: str | None = None,
        max_size_mb: int | None = None,
        ttl_hours: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._cache_dir = Path(cache_dir or settings.pdf_cache_dir)
        self._max_size_mb = max_size_mb or settings.pdf_cache_max_size_mb
        self._ttl_hours = ttl_hours or settings.pdf_cache_ttl_hours
        self._client = client
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "pdf_cache"

    def supports(self, source: SourceRead, content: EnrichedContent | None = None) -> bool:
        if not source.url:
            return False
        url_lower = source.url.lower()
        return url_lower.endswith(".pdf") or ".pdf" in url_lower

    def enrich(
        self, content: EnrichedContent, source: SourceRead, question: str
    ) -> EnrichedContent:
        url_hash = hashlib.sha256(source.url.encode()).hexdigest()[:16]
        cache_path = self._cache_dir / f"{url_hash}.pdf"

        if self._cache_valid(cache_path):
            logger.debug("PDF cache hit: %s", source.url)
            content.metadata["local_pdf_path"] = str(cache_path)
            content.metadata["pdf_cached"] = True
            return content

        logger.info("Downloading PDF to cache: %s", source.url)
        client = self._client or httpx.Client(timeout=30, follow_redirects=True)
        should_close = self._client is None
        try:
            response = client.get(source.url)
            response.raise_for_status()
            cache_path.write_bytes(response.content)
            content.metadata["local_pdf_path"] = str(cache_path)
            content.metadata["pdf_downloaded"] = True
            self._evict_if_needed()
        except httpx.HTTPError as exc:
            logger.warning("PDF download failed for %s: %s", source.url, exc)
            content.metadata["pdf_download_error"] = str(exc)
        finally:
            if should_close:
                client.close()
        return content

    def _cache_valid(self, path: Path) -> bool:
        if not path.exists():
            return False
        import time
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        return age_hours < self._ttl_hours

    def _evict_if_needed(self) -> None:
        files = sorted(
            self._cache_dir.glob("*.pdf"),
            key=lambda p: p.stat().st_mtime,
        )
        total_size = sum(f.stat().st_size for f in files)
        max_bytes = self._max_size_mb * 1024 * 1024
        while total_size > max_bytes and len(files) > 1:
            oldest = files.pop(0)
            total_size -= oldest.stat().st_size
            oldest.unlink()
            logger.debug("PDF cache evicted: %s", oldest.name)
