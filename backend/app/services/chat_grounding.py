from __future__ import annotations

import re

from app.db.models import ExtractedFact, ResearchTask, VerificationResult
from app.schemas.fact import ExtractedFactRead
from app.schemas.report import ReportRead
from app.services.answer_composer import compose_followup_answer
from app.services.answer_selection import select_facts_for_answer
from app.services.question_intent import parse_question_intent
from app.services.report_reader_text import REPORT_SECTION_SUMMARY, extract_report_section

_SUSPICIOUS_PHRASES = (
    "常规公开信息",
    "过往公开披露内容",
    "不来自您提到的特定报告",
    "无法验证其时效性和完整性",
    "请提供报告名称或来源",
    "当前请求涉及投资建议",
)

_DENIAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"报告(?:中)?没有"),
    re.compile(r"报告未包含"),
    re.compile(r"并未包含"),
    re.compile(r"没有包含"),
    re.compile(r"does\s+not\s+contain", re.IGNORECASE),
    re.compile(r"not\s+included", re.IGNORECASE),
    re.compile(r"\bno\s+data\b", re.IGNORECASE),
)

_ENGINEERING_PHRASES = (
    "核心发现",
    "证据缺口",
    "验证状态",
    "可追溯来源",
    "verified",
    "conflicted",
    "insufficient",
)


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
        if not self._looks_bad_followup(answer):
            return answer
        return self._build_deterministic_answer(
            task=task,
            message=message,
            report=report,
            facts=facts,
            verifications=verifications,
        )

    def _looks_bad_followup(self, answer: str) -> bool:
        if any(phrase in answer for phrase in _SUSPICIOUS_PHRASES):
            return True
        if any(pattern.search(answer) for pattern in _DENIAL_PATTERNS):
            return True
        return sum(1 for phrase in _ENGINEERING_PHRASES if phrase in answer) >= 2

    def _build_deterministic_answer(
        self,
        *,
        task: ResearchTask,
        message: str,
        report: ReportRead,
        facts: list[ExtractedFact],
        verifications: list[VerificationResult],
    ) -> str:
        summary = extract_report_section(report.content, REPORT_SECTION_SUMMARY)
        read_facts = [ExtractedFactRead.model_validate(f) for f in facts]
        verified_ids = {
            item.fact_id
            for item in verifications
            if str(getattr(item.status, "value", item.status)) == "verified"
        }
        pool = [fact for fact in read_facts if fact.id in verified_ids]
        plan = parse_question_intent(message or task.question)
        fact_set = select_facts_for_answer(
            question=message or task.question,
            facts=pool,
            plan=plan,
        )
        return compose_followup_answer(
            company_name=task.company_name,
            user_message=message,
            report_summary=summary,
            fact_set=fact_set,
            plan=plan,
        )
