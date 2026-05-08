from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.common import TaskStatus
from app.schemas.fact import ExtractedFactRead
from app.schemas.task import ResearchTaskRead
from app.schemas.verification import VerificationResultRead
from app.services.report_renderer import MockReportRenderer, ReportRenderInput


def _task() -> ResearchTaskRead:
    now = datetime.now(timezone.utc)
    return ResearchTaskRead(
        id="task_1",
        user_id="user_1",
        company_name="Renderer Co",
        question="Check renderer output",
        status=TaskStatus.COMPLETED,
        created_at=now,
        updated_at=now,
    )


def _task_with_question(question: str) -> ResearchTaskRead:
    task = _task()
    return task.model_copy(update={"question": question})


def _fact(*, fact_id: str, claim: str, metric_name: str = "revenue") -> ExtractedFactRead:
    return ExtractedFactRead(
        id=fact_id,
        task_id="task_1",
        claim=claim,
        metric_name=metric_name,
        value="100",
        period="2024",
        source_id=f"source_{fact_id}",
        chunk_id=f"chunk_{fact_id}",
        confidence=0.8,
        created_at=datetime.now(timezone.utc),
    )


def test_mock_report_renderer_keeps_template_out_of_provider_logic() -> None:
    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task(),
            risk_analysis="Renderer risk analysis.",
            outdated_facts=[_fact(fact_id="old", claim="old fact")],
            rejected_facts=[_fact(fact_id="bad", claim="bad fact")],
        )
    )

    assert report.task_id == "task_1"
    assert "Renderer Co" in report.title
    assert "Renderer risk analysis." in report.content
    assert "status=outdated" in report.content
    assert "old fact" in report.content
    assert "status=rejected" in report.content
    assert "bad fact" in report.content


def test_mock_report_renderer_calls_out_missing_rd_coverage() -> None:
    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task_with_question("近三年研发变化"),
            insufficient_facts=[_fact(fact_id="rev", claim="2024年营业收入为100亿元")],
        )
    )

    assert "## 研究问题覆盖情况" in report.content
    assert "未抽取到研发投入/研发费用事实" in report.content


def test_mock_report_renderer_includes_verification_explanation_summary() -> None:
    now = datetime.now(timezone.utc)
    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task(),
            verification_results=[
                VerificationResultRead(
                    id="v1",
                    fact_id="f1",
                    task_id="task_1",
                    status="verified",
                    confidence=0.88,
                    supporting_sources=["s1", "s2"],
                    conflicting_sources=[],
                    reason="单位归一化后一致",
                    reason_code="unit_normalized_match",
                    created_at=now,
                )
            ],
        )
    )

    assert "## 校验解释摘要" in report.content
    assert "单位归一化后多来源一致" in report.content


def test_mock_report_renderer_prioritizes_core_facts() -> None:
    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task_with_question("近三年研发投入变化"),
            core_facts=[
                _fact(
                    fact_id="rd",
                    claim="2024年研发投入为100亿元",
                    metric_name="R&D_expenditure",
                )
            ],
            supporting_facts=[_fact(fact_id="rev", claim="2024年营业收入为100亿元")],
            relevance_intents=["rd"],
        )
    )

    assert "## 核心事实" in report.content
    assert "2024年研发投入为100亿元" in report.content
    assert "## 旁支事实" in report.content
    assert "2024年营业收入为100亿元" in report.content
