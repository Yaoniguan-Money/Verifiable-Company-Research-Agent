from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import NamedTuple

from app.domain.metric_registry import get_metric_registry
from app.domain.report_limits import (
    MAX_AMBIGUITY_GROUPS,
    MAX_AMBIGUITY_VALUES_PER_GROUP,
    MAX_CONFLICTED_APPENDIX,
    MAX_CORE_FINDINGS_DISPLAY,
    MAX_OPTIONAL_CONTEXT_DISPLAY,
    MAX_OUTDATED_APPENDIX,
    MAX_REJECTED_APPENDIX,
)
from app.schemas.chunk import Citation
from app.schemas.common import ComplianceStatus
from app.schemas.fact import ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from app.services.answer_pipeline import AnswerContext
from app.services.report_reader_text import (
    fact_status_suffix_for_reader,
    format_risk_analysis_for_report,
    verification_status_label,
)


@dataclass(slots=True)
class ReportRenderInput:
    task: ResearchTaskRead
    core_facts: list[ExtractedFactRead] = field(default_factory=list)
    supporting_facts: list[ExtractedFactRead] = field(default_factory=list)
    relevance_intents: list[str] = field(default_factory=list)
    verified_facts: list[ExtractedFactRead] = field(default_factory=list)
    conflicted_facts: list[ExtractedFactRead] = field(default_factory=list)
    insufficient_facts: list[ExtractedFactRead] = field(default_factory=list)
    outdated_facts: list[ExtractedFactRead] = field(default_factory=list)
    rejected_facts: list[ExtractedFactRead] = field(default_factory=list)
    verification_results: list[VerificationResultRead] = field(default_factory=list)
    risk_analysis: str = ""
    citations: list[Citation] = field(default_factory=list)
    reader_summary: str | None = None
    answer_context: AnswerContext | None = None


class ReportDocumentRenderer:
    """Render the stable report Markdown schema from an AnswerContext."""

    def render(self, payload: ReportRenderInput) -> ReportCreate:
        ctx = payload.answer_context
        primary_facts = ctx.primary_facts if ctx else payload.core_facts
        optional_context = ctx.optional_context_facts if ctx else payload.supporting_facts
        summary = (ctx.summary_text if ctx else payload.reader_summary) or self._fallback_summary(
            payload
        )
        citation_view = self._citation_view(payload.citations)
        citation_index = citation_view.index_by_chunk
        status_by_fact = self._fact_status_map(payload.verification_results)
        verification_map = {item.fact_id: item for item in payload.verification_results}

        lines: list[str] = [
            f"# {payload.task.company_name} 公开信息研究报告",
            "",
            f"**研究问题**：{payload.task.question}",
            "",
            "> 本报告仅依据本次采集的公开资料整理，不构成投资建议。",
            "",
            "## 总结",
            summary,
            "",
            "## 核心发现",
            *self._build_fact_lines(
                primary_facts[:10],
                empty="暂未找到与该问题直接对应的可核对数据，建议查看文末来源或调整问题措辞。",
                citation_index=citation_index,
                status_by_fact=status_by_fact,
            ),
            *self._limit_notice("核心发现", len(primary_facts), MAX_CORE_FINDINGS_DISPLAY),
            "",
        ]

        if optional_context:
            lines.extend(
                [
                    "## 补充背景",
                    *self._build_fact_lines(
                        optional_context[:MAX_OPTIONAL_CONTEXT_DISPLAY],
                        empty="暂无额外补充背景。",
                        citation_index=citation_index,
                        status_by_fact=status_by_fact,
                    ),
                    *self._limit_notice(
                        "补充背景", len(optional_context), MAX_OPTIONAL_CONTEXT_DISPLAY
                    ),
                    "",
                ]
            )

        lines.extend(
            [
                "## 风险观察",
                *self._build_risk_lines(payload),
                "",
                "## 公开资料来源",
                *self._build_citation_lines(citation_view.items, len(payload.citations)),
                "",
                "## 附录",
                *self._build_appendix_lines(payload, verification_map, citation_index),
                "",
                "## 免责声明",
                "本报告基于公开资料生成，只用于信息研究，不构成投资建议。",
            ]
        )

        return ReportCreate(
            task_id=payload.task.id,
            title=f"{payload.task.company_name} - 企业公开信息研究报告",
            content="\n".join(lines),
            citations=payload.citations,
            compliance_status=ComplianceStatus.SKIPPED,
        )

    def _fallback_summary(self, payload: ReportRenderInput) -> str:
        facts = payload.core_facts or payload.verified_facts
        if facts:
            preview = "；".join(_readable_claim(f.claim) for f in facts[:3])
            return f"{payload.task.company_name}：{preview}。"
        return (
            f"本次采集的公开资料中，暂未找到可直接回答"
            f"「{payload.task.question}」的{payload.task.company_name}数据。"
        )

    def _build_appendix_lines(
        self,
        payload: ReportRenderInput,
        verification_map: dict[str, VerificationResultRead],
        citation_index: dict[tuple[str, str], int],
    ) -> list[str]:
        lines: list[str] = []
        total = (
            len(payload.verified_facts)
            + len(payload.conflicted_facts)
            + len(payload.insufficient_facts)
            + len(payload.outdated_facts)
            + len(payload.rejected_facts)
        )
        if total:
            rejected_count = len(payload.outdated_facts) + len(payload.rejected_facts)
            lines.append(
                f"- 数据核对：已采信 {len(payload.verified_facts)} 条，"
                f"口径差异 {len(payload.conflicted_facts)} 条，"
                f"证据不足 {len(payload.insufficient_facts)} 条"
                + (f"，已排除 {rejected_count} 条" if rejected_count else "")
                + "。"
            )
        elif payload.citations:
            lines.append("- 已采集公开资料来源，但尚未抽出足以支撑结论的结构化事实。")

        ctx = payload.answer_context
        if ctx and ctx.ambiguities:
            lines.append("- 口径差异说明：")
            for ambiguity in ctx.ambiguities[:MAX_AMBIGUITY_GROUPS]:
                value_text = "；".join(
                    _readable_claim(v.claim) for v in ambiguity.values[:MAX_AMBIGUITY_VALUES_PER_GROUP]
                )
                label = _readable_metric_label(ambiguity.comparable_metric)
                period_label = ambiguity.period if ambiguity.period != "unknown_period" else "期间未识别"
                lines.append(
                    f"  - {label}（{period_label}）：{value_text}"
                )
            lines.extend(
                self._limit_notice("口径差异", len(ctx.ambiguities), MAX_AMBIGUITY_GROUPS)
            )

        if "rd" in get_metric_registry().detect_families(payload.task.question) and not any(
            "r&d" in (f.metric_name or "").lower() or "研发" in f.claim
            for f in payload.verified_facts
        ):
            lines.append("- 问题涉及研发，但本次没有抽取到研发费用/投入类可核对数字。")

        for fact in payload.conflicted_facts[:MAX_CONFLICTED_APPENDIX]:
            ver = verification_map.get(fact.id)
            reason = ver.reason if ver else "同一指标同一期间存在不同取值。"
            ref = citation_index.get((fact.source_id, fact.chunk_id))
            suffix = f" 来源 {ref}" if ref else ""
            lines.append(f"- {fact.claim}：{reason}{suffix}")
        lines.extend(
            self._limit_notice("冲突条目", len(payload.conflicted_facts), MAX_CONFLICTED_APPENDIX)
        )

        for fact in payload.outdated_facts[:MAX_OUTDATED_APPENDIX]:
            lines.append(f"- {fact.claim}：来源或期间过时，未纳入主结论。")
        for fact in payload.rejected_facts[:MAX_REJECTED_APPENDIX]:
            lines.append(f"- {fact.claim}：已排除。")

        if not lines:
            lines.append("- 暂无需要单独说明的核对异常。")
        return lines

    def _build_fact_lines(
        self,
        facts: list[ExtractedFactRead],
        *,
        empty: str,
        citation_index: dict[tuple[str, str], int],
        status_by_fact: dict[str, str],
    ) -> list[str]:
        if not facts:
            return [f"- {empty}"]
        return [
            self._format_fact_line(
                fact,
                citation_index=citation_index,
                status=status_by_fact.get(fact.id),
            )
            for fact in facts
        ]

    def _format_fact_line(
        self,
        fact: ExtractedFactRead,
        *,
        citation_index: dict[tuple[str, str], int],
        status: str | None,
    ) -> str:
        suffix_parts: list[str] = []
        label = fact_status_suffix_for_reader(status)
        if label:
            suffix_parts.append(label)
        ref = citation_index.get((fact.source_id, fact.chunk_id))
        if ref:
            suffix_parts.append(f"来源 {ref}")
        suffix = f"（{'；'.join(suffix_parts)}）" if suffix_parts else ""
        return f"- {fact.claim}{suffix}"

    def _build_risk_lines(self, payload: ReportRenderInput) -> list[str]:
        lines: list[str] = []
        if payload.conflicted_facts and not payload.verified_facts:
            lines.append("- 不同来源说法不一致，且缺少可采信主事实；建议补充年报/半年报全文后重新查询。")
        elif payload.conflicted_facts:
            lines.append("- 不同来源说法不一致，部分指标存在口径差异，建议以年报合并报表原文为最终依据。")

        for bullet in format_risk_analysis_for_report(payload.risk_analysis):
            lines.append(f"- {bullet}")

        if not lines:
            lines.append("- 暂未发现需要特别关注的风险点。")
        return lines

    def _build_citation_lines(self, citations: list[Citation], raw_total: int | None = None) -> list[str]:
        if not citations:
            return ["- 当前没有可引用来源。"]
        lines: list[str] = []
        for idx, citation in enumerate(citations, start=1):
            url = (citation.url or "").strip()
            url_display = url or "无可打开 URL"
            lines.append(f"- [{idx}] {citation.title}：{url_display}")
        lines.extend(self._limit_notice("来源", raw_total or len(citations), 30))
        return lines

    def _limit_notice(self, label: str, total: int, limit: int) -> list[str]:
        if total <= limit:
            return []
        return [f"- 仅展示前 {limit} 条{label}；完整明细可在证据面板或 API 中查看。"]

    def _citation_view(self, citations: list[Citation]) -> CitationView:
        deduped: list[Citation] = []
        index_by_chunk: dict[tuple[str, str], int] = {}
        seen_urls: dict[str, int] = {}
        for citation in citations:
            url = (citation.url or "").strip()
            key = (citation.source_id, citation.chunk_id)
            if url and url in seen_urls:
                # 来源列表按 URL 去重；事实行也必须指向去重后的同一个编号。
                index_by_chunk[key] = seen_urls[url]
                continue
            deduped.append(citation)
            index = len(deduped)
            if url:
                seen_urls[url] = index
            index_by_chunk[key] = index
        return CitationView(items=deduped, index_by_chunk=index_by_chunk)

    def _fact_status_map(
        self,
        verification_results: list[VerificationResultRead],
    ) -> dict[str, str]:
        return {
            item.fact_id: str(getattr(item.status, "value", item.status))
            for item in verification_results
        }

    def _status_label(self, status: str) -> str:
        return verification_status_label(status)


def _readable_metric_label(comparable_metric: str) -> str:
    """Convert internal metric key to a human-readable Chinese label."""
    _METRIC_DISPLAY = {
        "r&d_expenditure": "研发费用",
        "r&d_total_spending": "研发投入合计",
        "revenue": "营业收入",
        "revenue_segment": "分业务收入",
        "net_profit": "净利润",
        "net_profit_parent": "归母净利润",
        "net_profit_deducted": "扣非净利润",
        "production_capacity": "产能",
        "production_volume": "产量",
        "sales_volume": "销量",
    }
    base = comparable_metric.split(":", 1)[0]
    return _METRIC_DISPLAY.get(base, base)


def _readable_claim(claim: str) -> str:
    """Clean a claim for display: strip garbled dimension fragments."""
    cleaned = re.sub(r"（来源\s*\d+[^）]*）\s*$", "", claim or "")
    cleaned = re.sub(r"期间未识别：", "", cleaned)
    return cleaned.strip()


class MockReportRenderer(ReportDocumentRenderer):
    """Backward-compatible renderer name used by tests and providers."""


class CitationView(NamedTuple):
    items: list[Citation]
    index_by_chunk: dict[tuple[str, str], int]
