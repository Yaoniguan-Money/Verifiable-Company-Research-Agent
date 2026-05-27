from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.schemas.common import SourceType
from app.schemas.source import SourceRead
from app.services.content_enrichment.base import EnrichedContent
from app.services.content_enrichment.section_annotator import SectionAnnotator
from app.services.content_enrichment.table_markdown import TableMarkdownEnricher


@dataclass
class _ParsedReport:
    tables_markdown: list[str] | None = None
    sections: list[object] | None = None
    report_year: str | None = None
    unit_note: str | None = None


@dataclass
class _Section:
    title: str
    content: str


def _source() -> SourceRead:
    now = datetime.now(timezone.utc)
    return SourceRead(
        id="source",
        task_id="task",
        title="source",
        url="https://example.com",
        source_type=SourceType.OTHER,
        retrieved_at=now,
        raw_content="raw",
        credibility_score=0.5,
        source_metadata={},
        created_at=now,
    )


def test_table_markdown_enricher_respects_zero_max_tables() -> None:
    content = EnrichedContent(
        raw="正文",
        parsed=_ParsedReport(tables_markdown=["| a |\n|---|"], report_year="2024"),
    )

    out = TableMarkdownEnricher(max_tables=0).enrich(content, _source(), "")

    assert out.raw == "正文"
    assert "tables_appended" not in out.metadata


def test_section_annotator_counts_actual_annotations() -> None:
    content = EnrichedContent(
        raw="第一节正文",
        parsed=_ParsedReport(
            sections=[
                _Section(title="第一节", content="第一节正文"),
                _Section(title="空节", content=" "),
            ]
        ),
    )

    out = SectionAnnotator().enrich(content, _source(), "")

    assert "<!-- SECTION: 第一节 -->" in out.raw
    assert out.metadata["sections_annotated"] == 1
