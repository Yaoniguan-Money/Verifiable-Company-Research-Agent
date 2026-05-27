from __future__ import annotations

import logging

from app.core.config import get_settings
from app.schemas.source import SourceRead
from app.services.content_enrichment.base import ContentEnricher, EnrichedContent
from app.services.rag.financial_report_parser import FinancialReportParser

logger = logging.getLogger(__name__)


class FinancialReportEnricher(ContentEnricher):
    """Parse PDF into structured ``ParsedReport`` using ``FinancialReportParser``.

    Requires ``local_pdf_path`` in content metadata (set by ``PDFCache``)
    or ``pdf_path`` / ``local_pdf_path`` in source metadata.
    """

    def __init__(self, *, max_sections: int | None = None, max_tables: int | None = None) -> None:
        settings = get_settings()
        self._max_sections = max_sections or settings.report_parser_max_sections
        self._max_tables = max_tables or settings.table_extraction_max_tables
        self._parser = FinancialReportParser()

    @property
    def name(self) -> str:
        return "financial_report"

    def supports(self, source: SourceRead, content: EnrichedContent | None = None) -> bool:
        meta = source.source_metadata or {}
        if meta.get("local_pdf_path") or meta.get("pdf_path"):
            return True
        if content is not None and content.metadata.get("local_pdf_path"):
            return True
        return False

    def enrich(
        self, content: EnrichedContent, source: SourceRead, question: str
    ) -> EnrichedContent:
        meta = source.source_metadata or {}
        pdf_path = (
            content.metadata.get("local_pdf_path")
            or meta.get("local_pdf_path")
            or meta.get("pdf_path")
        )
        if not pdf_path:
            return content

        try:
            parsed = self._parser.parse(str(pdf_path))
        except Exception as exc:
            logger.warning("FinancialReportParser failed for %s: %s", pdf_path, exc)
            content.metadata["parse_error"] = str(exc)
            return content

        content.parsed = parsed
        content.metadata["report_year"] = parsed.report_year
        content.metadata["auditor"] = parsed.auditor
        content.metadata["section_count"] = len(parsed.sections)
        content.metadata["table_count"] = len(parsed.tables_markdown)
        return content
