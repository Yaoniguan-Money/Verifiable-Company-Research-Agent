"""将选定事实组织为面向读者的自然语言回答。"""

from __future__ import annotations

import re

from app.domain.report_limits import (
    MAX_COMPOSER_FACTS_IN_PARAGRAPH,
    MAX_TREND_FACTS_IN_PARAGRAPH,
    VERIFICATION_CONFLICT_NOTE_THRESHOLD,
)
from app.schemas.fact import ExtractedFactRead
from app.services.answer_selection import AnswerFactSet
from app.services.question_intent import AnswerMode, AnswerPlan
from app.services.question_time_scope import period_year


def compose_report_answer(
    *,
    company_name: str,
    question: str,
    fact_set: AnswerFactSet,
    plan: AnswerPlan,
) -> str:
    """生成报告「总结」段：完整句子，直接回答问题。"""
    primary = fact_set.primary_facts

    if not primary:
        gap = "；".join(fact_set.gap_notes) if fact_set.gap_notes else ""
        base = (
            f"本次采集的公开资料中，暂未找到可直接回答「{question}」的{company_name}数据。"
        )
        if gap:
            return base + gap
        return base + "可尝试将问题收窄到具体年份和指标（例如「2024年研发费用」），或点击文末来源链接核对年报原文。"

    if plan.answer_mode == AnswerMode.TREND and len(primary) >= 2:
        body = _compose_trend_paragraph(primary)
    else:
        body = _compose_direct_paragraph(primary)

    text = f"针对「{question}」，{company_name}：{body}"

    for note in fact_set.gap_notes:
        if note not in text:
            text += note
            if not text.endswith("。"):
                text += "。"

    if (
        fact_set.verification_conflicted_count >= VERIFICATION_CONFLICT_NOTE_THRESHOLD
        and "口径差异" not in text
    ):
        text += "注：部分指标在不同来源中存在口径差异，建议以年报合并报表为准。"
    return text


def compose_followup_answer(
    *,
    company_name: str,
    user_message: str,
    report_summary: str,
    fact_set: AnswerFactSet | None = None,
    plan: AnswerPlan | None = None,
) -> str:
    """追问兜底：优先引用报告总结，否则用选定事实成段回答。"""
    if report_summary.strip():
        return (
            f"关于「{user_message}」：{report_summary.strip()} "
            "以上仅依据当前报告已写入的内容；更细的金额与来源见报告「核心发现」与文末来源。"
        )

    if fact_set and fact_set.primary_facts:
        body = _compose_direct_paragraph(
            fact_set.primary_facts[:MAX_COMPOSER_FACTS_IN_PARAGRAPH]
        )
        return f"关于「{user_message}」：{company_name}在现有材料中可概括为：{body}"

    return (
        f"关于「{user_message}」：当前报告尚未写入足以直接回答该点的可核对事实。"
        "请查看报告文末来源链接，或将问题收窄到具体年度与指标。"
    )


def _compose_direct_paragraph(facts: list[ExtractedFactRead]) -> str:
    parts: list[str] = []
    for fact in facts[:MAX_COMPOSER_FACTS_IN_PARAGRAPH]:
        cleaned = _clean_claim(fact.claim)
        if cleaned:
            parts.append(cleaned)
    if not parts:
        return "相关指标在材料中表述不完整，需结合来源原文核对。"
    body = "；".join(parts)
    if not body.endswith("。"):
        body += "。"
    return body


def _compose_trend_paragraph(facts: list[ExtractedFactRead]) -> str:
    by_year: list[tuple[int, str]] = []
    for fact in facts:
        year = period_year(fact.period)
        cleaned = _clean_claim(fact.claim)
        if cleaned:
            by_year.append((year or 0, cleaned))
    by_year.sort(key=lambda x: x[0])

    if len(by_year) >= 2:
        years = [y for y, _ in by_year if y]
        if years and max(years) - min(years) >= 1:
            lines = [text for _, text in by_year[:MAX_TREND_FACTS_IN_PARAGRAPH]]
            body = "；".join(lines)
            if not body.endswith("。"):
                body += "。"
            return f"从已核对条目看，{' → '.join(str(y) for y in sorted(set(years)) if y)} 年间相关数据为：{body}"

    return _compose_direct_paragraph(facts)


def _clean_claim(claim: str) -> str:
    text = (claim or "").strip()
    text = re.sub(r"（来源\s*\d+[^）]*）\s*$", "", text)
    text = re.sub(r"（[^）]*口径不一致[^）]*）\s*$", "", text)
    return text.strip()
