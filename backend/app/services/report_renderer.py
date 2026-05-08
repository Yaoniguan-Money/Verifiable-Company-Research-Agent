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
        verification_map = {item.fact_id: item for item in payload.verification_results}
        all_facts = [
            *payload.verified_facts,
            *payload.conflicted_facts,
            *payload.insufficient_facts,
            *payload.outdated_facts,
            *payload.rejected_facts,
        ]
        core_lines = [
            f"- {fact.claim}（metric={fact.metric_name or '-'}, source_id={fact.source_id}, chunk_id={fact.chunk_id}）"
            for fact in payload.core_facts[:12]
        ] or ["- 当前未识别到能直接回答研究问题的核心事实。"]
        supporting_lines = [
            f"- {fact.claim}（metric={fact.metric_name or '-'}）"
            for fact in payload.supporting_facts[:8]
        ] or ["- 当前没有额外旁支事实。"]

        verified_lines = [
            (
                f"- {fact.claim}（source_id={fact.source_id}, chunk_id={fact.chunk_id}, "
                f"confidence={fact.confidence:.2f}）"
            )
            for fact in payload.verified_facts
        ] or ["- 当前暂无高置信度已验证事实。"]

        conflicted_lines: list[str] = []
        for fact in payload.conflicted_facts:
            ver = verification_map.get(fact.id)
            conflicts = ",".join(ver.conflicting_sources) if ver else "未知冲突来源"
            reason = ver.reason if ver else "不同来源存在冲突"
            conflicted_lines.append(
                f"- {fact.claim}（不同来源存在冲突：{reason}，conflicting_sources={conflicts}）"
            )
        if not conflicted_lines:
            conflicted_lines = ["- 当前未发现明显数据冲突。"]

        insufficient_lines = [
            (
                f"- {fact.claim}（source_id={fact.source_id}, chunk_id={fact.chunk_id}，"
                "缺少独立来源验证）"
            )
            for fact in payload.insufficient_facts
        ] or ["- 当前未发现明显证据不足项。"]

        outdated_lines = [
            f"- status=outdated; {fact.claim}（source_id={fact.source_id}, chunk_id={fact.chunk_id}）"
            for fact in payload.outdated_facts
        ] or ["- 当前未发现明显过时来源。"]

        rejected_lines = [
            f"- status=rejected; {fact.claim}（source_id={fact.source_id}, chunk_id={fact.chunk_id}）"
            for fact in payload.rejected_facts
        ] or ["- 当前未发现被拒绝纳入结论的事实。"]

        citation_lines = [
            f"- source_id={c.source_id}, chunk_id={c.chunk_id}, title={c.title}"
            for c in payload.citations
        ] or ["- 当前无可引用来源，结论应按证据不足处理。"]

        content = "\n".join(
            [
                f"# {payload.task.company_name} 公开信息研究报告（Mock）",
                "",
                "## 企业概览",
                f"- 研究问题：{payload.task.question}",
                "",
                "## 研究问题覆盖情况",
                *self._build_coverage_lines(payload.task.question, all_facts),
                "",
                "## 核心事实（直接回答研究问题）",
                f"- 识别到的问题意图：{', '.join(payload.relevance_intents) if payload.relevance_intents else 'general'}",
                *core_lines,
                "",
                "## 旁支事实（仅作背景参考）",
                *supporting_lines,
                "",
                "## 校验解释摘要",
                *self._build_verification_explanation_lines(payload.verification_results),
                "",
                "## 已验证事实",
                *verified_lines,
                "",
                "## 存在冲突的事实 / 数据冲突提示",
                *conflicted_lines,
                "",
                "## 信息缺口 / 证据不足",
                *insufficient_lines,
                "",
                "## 过时来源",
                *outdated_lines,
                "",
                "## 被拒绝事实",
                *rejected_lines,
                "",
                "## 风险观察",
                "- 数据冲突可能来自口径差异、披露时点差异或统计范围不同，需持续核对。",
                "- 对证据不足项不形成确定性结论，应持续补充独立公开来源。",
                f"- {payload.risk_analysis}",
                "",
                "## 公开资料来源 / Citations",
                *citation_lines,
                "",
                "## 免责声明",
                "本报告基于公开资料生成，仅用于信息研究，不构成投资建议。",
            ]
        )

        return ReportCreate(
            task_id=payload.task.id,
            title=f"{payload.task.company_name} —— 企业公开信息研究报告（Mock）",
            content=content,
            citations=payload.citations,
            compliance_status=ComplianceStatus.SKIPPED,
        )

    def _build_coverage_lines(
        self,
        question: str,
        facts: list[ExtractedFactRead],
    ) -> list[str]:
        lines: list[str] = []
        if "研发" in question and not any(f.metric_name == "R&D_expenditure" for f in facts):
            lines.append("- 未抽取到研发投入/研发费用事实；报告只能说明当前公开资料证据缺口。")
        if any(f.period == "unknown_period" for f in facts):
            lines.append("- 部分事实未识别到明确期间，已按证据不足处理，不用于趋势结论。")
        if not facts:
            lines.append("- 当前未抽取到结构化事实，需补充更充分的原始资料。")
        return lines or ["- 当前抽取到的结构化事实可覆盖研究问题的部分维度。"]

    def _build_verification_explanation_lines(
        self,
        verification_results: list[VerificationResultRead],
    ) -> list[str]:
        if not verification_results:
            return ["- 当前没有可解释的校验结果。"]

        counts: dict[str, int] = {}
        for item in verification_results:
            code = item.reason_code or "unknown_reason"
            counts[code] = counts.get(code, 0) + 1

        descriptions = {
            "same_value_multi_source": "多来源同指标同期间取值一致",
            "unit_normalized_match": "单位归一化后多来源一致",
            "metric_alias_normalized_match": "指标别名归一化后多来源一致",
            "metric_and_unit_normalized_match": "指标别名与单位均归一化后多来源一致",
            "different_value_multi_source": "多来源同指标同期间取值不同",
            "single_source_only": "只有单一来源，暂不形成高置信结论",
            "outdated_period_or_source": "来源或事实期间过旧",
            "invalid_numeric_value": "数值异常，已拒绝",
            "low_credibility_source": "来源可信度过低，已拒绝",
            "missing_source_id": "缺少来源标识，无法追溯",
            "missing_required_fields": "缺少事实关键字段",
        }

        return [
            f"- {descriptions.get(code, code)}：{count} 条"
            for code, count in sorted(counts.items())
        ]
