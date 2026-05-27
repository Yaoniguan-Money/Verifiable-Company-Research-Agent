"""报告总结段生成测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.fact import ExtractedFactRead
from app.services.answer_pipeline import AnswerPipeline


def _fact(*, claim: str, period: str = "2024") -> ExtractedFactRead:
    return ExtractedFactRead(
        id="f1",
        task_id="t1",
        claim=claim,
        metric_name="net_profit",
        value="228.65亿元",
        period=period,
        source_id="s1",
        chunk_id="c1",
        confidence=0.9,
        created_at=datetime.now(timezone.utc),
    )


def test_summary_uses_prose_not_bullets() -> None:
    ctx = AnswerPipeline().build_context(
        company_name="某A股新能源上市公司",
        question="近两年利润",
        verified_facts=[_fact(claim="2024年归母净利润为228.65亿元（来源 16）")],
        verifications=[],
    )
    text = ctx.summary_text
    assert "针对「近两年利润」" in text
    assert "228.65亿元" in text
    assert "近2年" in text or "近两年" in text
    assert text.count("- ") < 2


def test_extract_summary_section() -> None:
    from app.services.report_reader_text import extract_report_section

    content = "## 总结\n这是一段连贯文字。\n\n## 核心发现\n- 条目"
    assert extract_report_section(content, "总结") == "这是一段连贯文字。"
