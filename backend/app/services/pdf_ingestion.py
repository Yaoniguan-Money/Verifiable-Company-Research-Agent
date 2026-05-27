"""PDF 来源正文增强。"""

from __future__ import annotations

from app.services.rag.financial_report_parser import FinancialReportParser


def enrich_pdf_raw_content(raw_content: str, source_metadata: dict | None) -> str:
    meta = source_metadata or {}
    pdf_path = meta.get("pdf_path") or meta.get("local_pdf_path")
    if not pdf_path:
        return raw_content
    try:
        parsed = FinancialReportParser().parse(str(pdf_path))
    except Exception:
        return raw_content
    parts = [raw_content, f"\n\n# 财报结构化解析\n报告年度：{parsed.report_year or '未知'}"]
    if parsed.unit_note:
        parts.append(parsed.unit_note)
    for section in parsed.sections[:12]:
        parts.append(f"\n## {section.title}\n{section.content[:4000]}")
    for table in parsed.tables_markdown[:6]:
        parts.append(f"\n{table}")
    return "\n".join(parts)
