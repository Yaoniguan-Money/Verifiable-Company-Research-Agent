"""财报 PDF 结构化解析（pdfplumber）。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ParsedSection:
    title: str
    content: str


@dataclass
class ParsedReport:
    company_name: str | None = None
    report_year: str | None = None
    auditor: str | None = None
    sections: list[ParsedSection] = field(default_factory=list)
    tables_markdown: list[str] = field(default_factory=list)
    unit_note: str | None = None


class FinancialReportParser:
    """中国上市公司年报/半年报的结构化解析。"""

    SECTION_PATTERN = re.compile(
        r"^(第[一二三四五六七八九十]+节|[一二三四五六七八九十]+、)\s*(.+)$"
    )
    YEAR_PATTERN = re.compile(r"(20\d{2})\s*年(?:度|报)")
    AUDITOR_PATTERN = re.compile(r"审计机构[：:]\s*(.+)")

    def parse(self, pdf_path: str) -> ParsedReport:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(pdf_path)

        try:
            import pdfplumber  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError("请安装 pdfplumber: pip install pdfplumber") from exc

        report = ParsedReport()
        full_lines: list[str] = []
        tables_md: list[str] = []

        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text:
                    full_lines.extend(text.splitlines())
                for table in page.extract_tables() or []:
                    md = self._table_to_markdown(table)
                    if md:
                        tables_md.append(md)

        report.tables_markdown = tables_md
        body = "\n".join(full_lines)
        report.report_year = self._extract_year(body)
        report.auditor = self._extract_auditor(body)
        report.unit_note = self._extract_unit_note(body)
        report.sections = self._split_sections(full_lines)
        return report

    def _split_sections(self, lines: list[str]) -> list[ParsedSection]:
        sections: list[ParsedSection] = []
        current_title = "正文"
        buffer: list[str] = []
        for line in lines:
            m = self.SECTION_PATTERN.match(line.strip())
            if m:
                if buffer:
                    sections.append(ParsedSection(title=current_title, content="\n".join(buffer)))
                current_title = m.group(2).strip()
                buffer = []
            else:
                buffer.append(line)
        if buffer:
            sections.append(ParsedSection(title=current_title, content="\n".join(buffer)))
        return sections

    @staticmethod
    def _table_to_markdown(table: list[list[str | None]]) -> str:
        rows = [[(cell or "").strip() for cell in row] for row in table if row]
        if not rows:
            return ""
        header = rows[0]
        sep = ["---"] * len(header)
        body = rows[1:] if len(rows) > 1 else []
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(sep) + " |",
        ]
        for row in body:
            padded = row + [""] * (len(header) - len(row))
            lines.append("| " + " | ".join(padded[: len(header)]) + " |")
        return "\n".join(lines)

    def _extract_year(self, text: str) -> str | None:
        m = self.YEAR_PATTERN.search(text)
        return m.group(1) if m else None

    def _extract_auditor(self, text: str) -> str | None:
        m = self.AUDITOR_PATTERN.search(text)
        return m.group(1).strip() if m else None

    @staticmethod
    def _extract_unit_note(text: str) -> str | None:
        for pattern in (r"单位[：:]\s*万元", r"单位[：:]\s*亿元", r"单位[：:]\s*元"):
            m = re.search(pattern, text)
            if m:
                return m.group(0)
        return None
