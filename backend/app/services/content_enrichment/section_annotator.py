from __future__ import annotations

from app.schemas.source import SourceRead
from app.services.content_enrichment.base import ContentEnricher, EnrichedContent


class SectionAnnotator(ContentEnricher):
    """Insert section boundary markers into raw content.

    These markers are consumed by ``SectionAwareChunker`` to split at
    semantically meaningful boundaries instead of arbitrary character offsets.

    Marker format: ``\\n\\n<!-- SECTION: {title} -->\\n``
    """

    SECTION_MARKER_PREFIX = "\n\n<!-- SECTION: "
    SECTION_MARKER_SUFFIX = " -->\n"

    @property
    def name(self) -> str:
        return "section_annotator"

    def supports(self, source: SourceRead, content: EnrichedContent | None = None) -> bool:
        return True

    def enrich(
        self, content: EnrichedContent, source: SourceRead, question: str
    ) -> EnrichedContent:
        parsed = content.parsed
        if parsed is None:
            return content

        sections = getattr(parsed, "sections", None) or []
        if not sections:
            return content

        text = content.raw
        annotated = 0
        for section in sections:
            title = getattr(section, "title", "") or ""
            content_text = getattr(section, "content", "") or ""
            if not content_text.strip():
                continue
            marker = f"{self.SECTION_MARKER_PREFIX}{title}{self.SECTION_MARKER_SUFFIX}"
            pos = text.find(content_text[:120])
            if pos == -1:
                text += marker + content_text
                annotated += 1
            elif marker not in text:
                text = text[:pos] + marker + text[pos:]
                annotated += 1

        content.raw = text
        content.metadata["sections_annotated"] = annotated
        return content
