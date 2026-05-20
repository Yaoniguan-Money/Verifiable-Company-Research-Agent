from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.chunk import Citation
from app.schemas.common import ComplianceStatus
from app.schemas.fact import ExtractedFactRead
from app.schemas.report import ReportCreate
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead


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


class MockReportRenderer:
    """Deterministic report renderer for mock/rule-based provider paths."""

    def render(self, payload: ReportRenderInput) -> ReportCreate:
        citation_index = self._citation_index(payload.citations)
        status_by_fact = self._fact_status_map(payload.verification_results)
        verification_map = {item.fact_id: item for item in payload.verification_results}
        all_facts = [
            *payload.verified_facts,
            *payload.conflicted_facts,
            *payload.insufficient_facts,
            *payload.outdated_facts,
            *payload.rejected_facts,
        ]
        direct_facts = payload.core_facts or payload.verified_facts[:12]

        content = "\n".join(
            [
                f"# {payload.task.company_name} 公开信息研究报告",
                "",
                "> 这份报告只基于本次采集到的公开资料。没有被来源支持的判断，不写成确定结论。",
                "",
                "## 企业概览",
                f"- 研究对象：{payload.task.company_name}",
                f"- 研究问题：{payload.task.question}",
                f"- 本次可回查来源：{len(payload.citations)} 条",
                "",
                "## 先说结论",
                *self._build_executive_summary_lines(payload),
                "",
                "## 这份报告覆盖到了什么",
                *self._build_coverage_lines(payload.task.question, all_facts),
                "",
                "## 核心事实：能直接回答问题的内容",
                *self._build_fact_lines(
                    direct_facts[:12],
                    empty="这次没有抽取到可以直接回答问题的可靠事实。",
                    citation_index=citation_index,
                    status_by_fact=status_by_fact,
                ),
                *self._limit_notice("核心事实", len(direct_facts), 12),
                "",
                "## 补充背景",
                *self._build_fact_lines(
                    payload.supporting_facts[:8],
                    empty="这次没有额外的补充背景事实。",
                    citation_index=citation_index,
                    status_by_fact=status_by_fact,
                ),
                *self._limit_notice("补充背景事实", len(payload.supporting_facts), 8),
                "",
                "## 可信度说明",
                *self._build_confidence_lines(payload),
                *self._build_verification_explanation_lines(payload.verification_results),
                "",
                "## 需要谨慎的地方",
                *self._build_caution_lines(payload, verification_map, citation_index),
                "",
                "## 风险观察",
                *self._build_risk_lines(payload, all_facts),
                "",
                "## 公开资料来源",
                *self._build_citation_lines(payload.citations),
                "",
                "## 免责声明",
                "本报告基于公开资料生成，只用于信息研究，不构成投资建议。",
            ]
        )

        return ReportCreate(
            task_id=payload.task.id,
            title=f"{payload.task.company_name} —— 企业公开信息研究报告",
            content=content,
            citations=payload.citations,
            compliance_status=ComplianceStatus.SKIPPED,
        )

    def _build_executive_summary_lines(self, payload: ReportRenderInput) -> list[str]:
        all_fact_count = (
            len(payload.verified_facts)
            + len(payload.conflicted_facts)
            + len(payload.insufficient_facts)
            + len(payload.outdated_facts)
            + len(payload.rejected_facts)
        )
        source_count = len(payload.citations)

        if not all_fact_count:
            if source_count:
                return [
                    f"- 对“{payload.task.question}”：本次还不能可靠回答。",
                    (
                        f"- 系统找到了 {source_count} 条可回查来源，但没有从中抽取到能支撑结论的结构化事实。"
                    ),
                    "- 现有材料只能当作线索，不能据此总结趋势、利润来源、经营变化或风险强弱。",
                ]
            return [
                f"- 对“{payload.task.question}”：本次还不能回答。",
                "- 原因是没有找到可回查来源，也没有可核验事实。",
                "- 需要补充公开披露正文、公告、年报或其他权威来源后再判断。",
            ]

        if payload.core_facts:
            first_line = (
                f"- 对“{payload.task.question}”：本次找到了 "
                f"{len(payload.core_facts)} 条直接相关事实。"
            )
        elif payload.verified_facts:
            first_line = (
                f"- 对“{payload.task.question}”：本次有 "
                f"{len(payload.verified_facts)} 条已验证事实可参考，但与问题的直接匹配度有限。"
            )
        else:
            first_line = f"- 对“{payload.task.question}”：目前只有待核实线索，不能写成确定结论。"

        lines = [first_line]
        if payload.verified_facts:
            lines.append(f"- 可较稳妥引用的事实：{len(payload.verified_facts)} 条。")
        if payload.conflicted_facts or payload.insufficient_facts:
            lines.append(
                "- 仍需谨慎："
                f"冲突 {len(payload.conflicted_facts)} 条，"
                f"证据不足 {len(payload.insufficient_facts)} 条。"
            )
        if payload.outdated_facts or payload.rejected_facts:
            lines.append(
                "- 已排除在结论外："
                f"过时 {len(payload.outdated_facts)} 条，"
                f"质量不够或字段异常 {len(payload.rejected_facts)} 条。"
            )
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
        notes: list[str] = []
        if status:
            notes.append(self._status_label(status))
        ref = citation_index.get((fact.source_id, fact.chunk_id))
        if ref:
            notes.append(f"来源：引用 {ref}")
        if fact.confidence is not None:
            notes.append(f"抽取置信度约 {round(fact.confidence * 100)}%")
        suffix = f"（{'；'.join(notes)}）" if notes else ""
        return f"- {fact.claim}{suffix}"

    def _build_confidence_lines(self, payload: ReportRenderInput) -> list[str]:
        total = (
            len(payload.verified_facts)
            + len(payload.conflicted_facts)
            + len(payload.insufficient_facts)
            + len(payload.outdated_facts)
            + len(payload.rejected_facts)
        )
        if total == 0:
            return ["- 本次没有进入校验环节的事实，因此没有可信度分层。"]

        lines = [
            f"- 已验证：{len(payload.verified_facts)} 条。",
            f"- 证据不足：{len(payload.insufficient_facts)} 条。",
            f"- 来源口径冲突：{len(payload.conflicted_facts)} 条。",
            f"- 过时或不适合采用：{len(payload.outdated_facts) + len(payload.rejected_facts)} 条。",
        ]
        if payload.verified_facts:
            lines.append("- 使用建议：优先阅读“核心事实”，再通过“公开资料来源”回查原文。")
        else:
            lines.append("- 使用建议：目前不应把任何待核实信息写成确定结论。")
        return lines

    def _build_caution_lines(
        self,
        payload: ReportRenderInput,
        verification_map: dict[str, VerificationResultRead],
        citation_index: dict[tuple[str, str], int],
    ) -> list[str]:
        lines: list[str] = []
        if not (
            payload.verified_facts
            or payload.conflicted_facts
            or payload.insufficient_facts
            or payload.outdated_facts
            or payload.rejected_facts
        ):
            if payload.citations:
                return [
                    "- 虽然有来源，但没有抽取到可核验事实。报告只能说明“证据不足”，不能代替结论。",
                    "- 如果问题需要财务拆分、利润板块、趋势变化，应优先补充年报、公告或交易所披露正文。",
                ]
            return ["- 目前缺少来源和事实，无法进行可靠判断。"]

        for fact in payload.conflicted_facts[:6]:
            ver = verification_map.get(fact.id)
            reason = ver.reason if ver else "不同来源口径不一致"
            lines.append(f"- {fact.claim}：不同来源说法不一致，原因是{reason}。")
        lines.extend(self._limit_notice("冲突事实", len(payload.conflicted_facts), 6))

        for fact in payload.insufficient_facts[:8]:
            ref = citation_index.get((fact.source_id, fact.chunk_id))
            ref_text = f"引用 {ref}" if ref else "当前来源"
            lines.append(f"- {fact.claim}：只由{ref_text}支撑，还需要更权威或第二个独立来源。")
        lines.extend(self._limit_notice("证据不足事实", len(payload.insufficient_facts), 8))

        for fact in payload.outdated_facts[:4]:
            lines.append(f"- {fact.claim}：来源或期间过旧，未纳入主要结论。")
        lines.extend(self._limit_notice("过时事实", len(payload.outdated_facts), 4))

        for fact in payload.rejected_facts[:4]:
            lines.append(f"- {fact.claim}：字段异常或来源质量不足，已排除。")
        lines.extend(self._limit_notice("已排除事实", len(payload.rejected_facts), 4))

        return lines or ["- 暂未发现需要单独提示的证据冲突或明显信息缺口。"]

    def _build_risk_lines(
        self,
        payload: ReportRenderInput,
        all_facts: list[ExtractedFactRead],
    ) -> list[str]:
        lines: list[str] = []
        if not all_facts:
            lines.append("- 最大风险不是经营判断本身，而是证据不够：当前材料不足以支持明确结论。")
        if payload.conflicted_facts:
            lines.append("- 数据口径存在冲突，继续使用前需要回到原始披露逐条核对。")
        if payload.insufficient_facts and not payload.verified_facts:
            lines.append("- 目前事实主要停留在线索层面，适合继续检索，不适合直接写成结论。")

        cleaned = self._clean_risk_text(payload.risk_analysis)
        if cleaned:
            lines.append(f"- {cleaned}")
        if not lines:
            lines.append("- 当前没有额外风险观察；后续应持续关注新披露和来源一致性。")
        return lines

    def _build_citation_lines(self, citations: list[Citation]) -> list[str]:
        if not citations:
            return ["- 当前没有可引用来源。"]
        lines = []
        for idx, citation in enumerate(citations[:30], start=1):
            url = citation.url or "无可打开 URL"
            lines.append(f"- [{idx}] {citation.title}：{url}")
        lines.extend(self._limit_notice("来源", len(citations), 30))
        return lines

    def _limit_notice(self, label: str, total: int, limit: int) -> list[str]:
        if total <= limit:
            return []
        return [f"- 只展示前 {limit} 条{label}；完整明细可在证据面板或 API 中查看。"]

    def _build_coverage_lines(
        self,
        question: str,
        facts: list[ExtractedFactRead],
    ) -> list[str]:
        lines: list[str] = []
        if "研发" in question and not any(f.metric_name == "R&D_expenditure" for f in facts):
            lines.append("- 问题涉及研发，但本次没有抽取到研发投入或研发费用数据。")
        if any(f.period == "unknown_period" for f in facts):
            lines.append("- 部分事实没有明确期间，只能作为背景线索，不能用于趋势判断。")
        if not facts:
            lines.append("- 还没有可核验事实；本轮覆盖程度不足。")
        return lines or ["- 本次事实可以覆盖研究问题的一部分，但仍建议结合原始披露复核。"]

    def _build_verification_explanation_lines(
        self,
        verification_results: list[VerificationResultRead],
    ) -> list[str]:
        if not verification_results:
            return []

        counts: dict[str, int] = {}
        for item in verification_results:
            code = item.reason_code or "unknown_reason"
            counts[code] = counts.get(code, 0) + 1

        descriptions = {
            "same_value_multi_source": "多个来源给出同一数值",
            "unit_normalized_match": "单位换算后可以对上",
            "metric_alias_normalized_match": "指标名称不同，但含义可以对上",
            "metric_and_unit_normalized_match": "指标名称和单位换算后都能对上",
            "different_value_multi_source": "多个来源给出的数值不同",
            "single_source_only": "只有一个来源支撑",
            "outdated_period_or_source": "来源或事实期间偏旧",
            "invalid_numeric_value": "数值字段异常",
            "low_credibility_source": "来源可信度偏低",
            "missing_source_id": "缺少来源标识，无法回查",
            "missing_required_fields": "事实缺少必要字段",
        }

        return [
            f"- 校验说明：{descriptions.get(code, code)}，共 {count} 条。"
            for code, count in sorted(counts.items())
        ]

    def _citation_index(self, citations: list[Citation]) -> dict[tuple[str, str], int]:
        return {
            (citation.source_id, citation.chunk_id): idx
            for idx, citation in enumerate(citations, start=1)
        }

    def _fact_status_map(
        self,
        verification_results: list[VerificationResultRead],
    ) -> dict[str, str]:
        return {
            item.fact_id: str(getattr(item.status, "value", item.status))
            for item in verification_results
        }

    def _status_label(self, status: str) -> str:
        labels = {
            "verified": "已验证",
            "conflicted": "存在口径冲突",
            "insufficient": "证据不足",
            "outdated": "来源或期间偏旧",
            "rejected": "已排除",
        }
        return labels.get(status, status)

    def _clean_risk_text(self, text: str) -> str:
        cleaned = " ".join(part.strip(" -*\t") for part in text.splitlines() if part.strip())
        for prefix in ("根据您的要求，", "根据您的要求,", "基于当前报告，", "基于当前报告,"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
        return cleaned
