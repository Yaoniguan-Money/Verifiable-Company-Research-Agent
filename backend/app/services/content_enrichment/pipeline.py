from __future__ import annotations

import logging

from app.schemas.source import SourceRead
from app.services.content_enrichment.base import ContentEnricher, EnrichedContent

logger = logging.getLogger(__name__)


class ContentEnrichmentPipeline:
    """Composable pipeline that runs enrichment stages sequentially.

    Each stage is skipped when ``supports()`` returns False for the source.
    """

    def __init__(self, stages: list[ContentEnricher]) -> None:
        self._stages = stages

    def enrich(self, source: SourceRead, question: str) -> EnrichedContent:
        content = EnrichedContent(raw=source.raw_content or "")
        for stage in self._stages:
            if not stage.supports(source, content):
                continue
            try:
                content = stage.enrich(content, source, question)
                content.metadata.setdefault("enrichment_stages", []).append(stage.name)
            except Exception:
                logger.exception("Enricher %s failed for source %s", stage.name, source.id)
                content.metadata.setdefault("enrichment_errors", []).append(stage.name)
        return content
