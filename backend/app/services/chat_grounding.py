from __future__ import annotations

from app.db.models import ExtractedFact, ResearchTask, VerificationResult
from app.schemas.report import ReportRead


class GroundedFollowupAnswerBuilder:
    """追问回答兜底器。

    LLM 可以负责组织语言，但不能把报告外常识包装成当前证据；当回答偏离报告时，
    这里用确定性模板把答案拉回 citations/facts/verification 链路。
    """

    def ensure_report_grounded_answer(
        self,
        *,
        answer: str,
        task: ResearchTask,
        message: str,
        report: ReportRead,
        facts: list[ExtractedFact],
        verifications: list[VerificationResult],
        verification_counts: dict[str, int],
    ) -> str:
        if not self._looks_ungrounded_followup(answer):
            return answer
        return self._build_deterministic_answer(
            task=task,
            message=message,
            report=report,
            facts=facts,
            verifications=verifications,
            verification_counts=verification_counts,
        )

    def _looks_ungrounded_followup(self, answer: str) -> bool:
        suspicious_phrases = (
            "常规公开信息",
            "过往公开披露内容",
            "不来自您提到的特定报告",
            "无法验证其时效性和完整性",
            "请提供报告名称或来源",
            "当前请求涉及投资建议",
        )
        return any(phrase in answer for phrase in suspicious_phrases)

    def _build_deterministic_answer(
        self,
        *,
        task: ResearchTask,
        message: str,
        report: ReportRead,
        facts: list[ExtractedFact],
        verifications: list[VerificationResult],
        verification_counts: dict[str, int],
    ) -> str:
        fact_lines = [
            f"- {fact.claim}（验证状态：{self._status_for_fact(fact, verifications)}）"
            for fact in facts[:5]
        ] or ["- 当前报告没有抽取到结构化事实。"]
        coverage_note = self._extract_report_section(report.content, "研究问题覆盖情况")
        coverage_text = coverage_note or "当前报告未提供额外覆盖说明。"
        return "\n".join(
            [
                f"基于当前报告回答“{message}”：",
                "",
                "1. 当前报告内可用证据如下：",
                *fact_lines,
                "",
                f"2. 验证状态统计：{verification_counts or {'none': 0}}。",
                "",
                f"3. 研究问题覆盖情况：{coverage_text}",
                "",
                "结论：以上回答只基于当前报告和其 citations。若报告没有抽取到研发投入/研发费用等直接指标，"
                "系统不会补充报告外常识，也不会形成确定性研发趋势结论。",
            ]
        )

    def _status_for_fact(self, fact: ExtractedFact, verifications: list[VerificationResult]) -> str:
        for item in verifications:
            if item.fact_id == fact.id:
                return getattr(item.status, "value", str(item.status))
        return "unknown"

    def _extract_report_section(self, content: str, heading: str) -> str:
        marker = f"## {heading}"
        if marker not in content:
            return ""
        tail = content.split(marker, 1)[1]
        section = tail.split("\n## ", 1)[0]
        return " ".join(line.strip("- ").strip() for line in section.splitlines() if line.strip())
