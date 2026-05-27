from __future__ import annotations

from app.core.config import get_settings
from app.schemas.source import SourceRead
from app.services.content_enrichment.base import ContentEnricher, EnrichedContent


class TableMarkdownEnricher(ContentEnricher):
    """Append parsed table markdown to the raw content text.

    Requires ``EnrichedContent.parsed`` to be set (by ``FinancialReportEnricher``).
    Each table is prefixed with a heading for downstream chunking awareness.
    """

    def __init__(self, *, max_tables: int | None = None) -> None:
        settings = get_settings()
        self._max_tables = (
            settings.table_extraction_max_tables if max_tables is None else max(0, max_tables)
        )

    @property
    def name(self) -> str:
        return "table_markdown"

    def supports(self, source: SourceRead, content: EnrichedContent | None = None) -> bool:
        return True

    def enrich(
        self, content: EnrichedContent, source: SourceRead, question: str
    ) -> EnrichedContent:
        parsed = content.parsed
        if parsed is None:
            return content
        tables = getattr(parsed, "tables_markdown", None) or []
        if not tables or self._max_tables <= 0:
            return content

        parts = [content.raw, "\n\n# 结构化表格"]
        for idx, table in enumerate(tables[: self._max_tables], start=1):
            parts.append(f"\n## 表格 {idx}\n{table}")
        report_year = getattr(parsed, "report_year", None) or "未知"
        unit_note = getattr(parsed, "unit_note", None)
        parts.insert(1, f"报告年度：{report_year}")
        if unit_note:
            parts.insert(2, unit_note)

        content.raw = "\n".join(parts)
        content.metadata["tables_appended"] = min(len(tables), self._max_tables)
        return content
