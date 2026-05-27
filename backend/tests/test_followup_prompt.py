from __future__ import annotations

from datetime import datetime, timezone

from app.db.models.research_task import TaskStatus
from app.schemas.common import ComplianceStatus
from app.schemas.report import ReportRead
from app.schemas.task import ResearchTaskRead
from app.services.followup_answer import FollowupPayload
from app.services.followup_prompt import build_followup_llm_prompt, truncate_followup_text


def test_build_followup_llm_prompt_includes_structured_facts() -> None:
    now = datetime.now(timezone.utc)
    task = ResearchTaskRead(
        id="task-1",
        user_id="user-1",
        company_name="Example Co",
        question="研发投入",
        status=TaskStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )
    report = ReportRead(
        id="report-1",
        task_id="task-1",
        title="report",
        content="## 总结\n已有研发投入信息。",
        citations=[],
        compliance_status=ComplianceStatus.PASSED,
        created_at=now,
    )
    payload = FollowupPayload(
        summary_excerpt="已有研发投入信息。",
        primary_facts_json='[{"claim":"2025年研发投入为10亿元"}]',
        ambiguities=[{"metric": "r_and_d", "period": "2025"}],
        citation_lines=["- source_1:chunk_1 2025年研发投入为10亿元"],
    )

    prompt = build_followup_llm_prompt(
        task=task,
        message="2025年研发投入是多少？",
        report=report,
        followup_payload=payload,
    )

    assert "followup_facts_json" in prompt
    assert "2025年研发投入为10亿元" in prompt
    assert "do not say the report lacks" in prompt
    assert "不得声称报告缺少" in prompt


def test_truncate_followup_text_handles_non_positive_limit() -> None:
    assert truncate_followup_text("abc", limit=0) == ""
    assert truncate_followup_text("abc", limit=-1) == ""
