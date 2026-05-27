from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ReportSection:
    id: str
    title: str
    lines: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReportDocument:
    title: str
    preface_lines: list[str] = field(default_factory=list)
    primary_sections: list[ReportSection] = field(default_factory=list)
    appendix_sections: list[ReportSection] = field(default_factory=list)
    disclaimer: str | None = None

