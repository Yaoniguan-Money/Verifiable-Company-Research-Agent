from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.chunk import Citation
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
    assert "来源或期间过旧" in report.content
    assert "old fact" in report.content
    assert "字段异常或来源质量不足" in report.content
    assert "bad fact" in report.content
    assert "source_id=" not in report.content
    assert "chunk_id=" not in report.content


def test_mock_report_renderer_calls_out_missing_rd_coverage() -> None:
    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task_with_question("近三年研发变化"),
            insufficient_facts=[_fact(fact_id="rev", claim="2024年营业收入为100亿元")],
        )
    )

    assert "## 这份报告覆盖到了什么" in report.content
    assert "没有抽取到研发投入或研发费用数据" in report.content


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

    assert "## 可信度说明" in report.content
    assert "单位换算后可以对上" in report.content


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
    assert "## 补充背景" in report.content
    assert "2024年营业收入为100亿元" in report.content


def test_mock_report_renderer_limits_noisy_detail_sections() -> None:
    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task(),
            conflicted_facts=[
                _fact(fact_id=f"conflict_{idx}", claim=f"冲突事实 {idx}") for idx in range(20)
            ],
            insufficient_facts=[
                _fact(fact_id=f"insufficient_{idx}", claim=f"不足事实 {idx}") for idx in range(20)
            ],
        )
    )

    assert "只展示前 6 条冲突事实" in report.content
    assert "只展示前 8 条证据不足事实" in report.content


def test_mock_report_renderer_marks_cited_but_unextracted_evidence_as_gap() -> None:
    now = datetime.now(timezone.utc)
    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task_with_question("近三年财报能看出啥"),
            citations=[
                Citation(
                    source_id="source_1",
                    chunk_id="chunk_1",
                    url="https://example.com/report.pdf",
                    title="样例年报",
                    retrieved_at=now,
                )
            ],
        )
    )

    assert "没有从中抽取到能支撑结论的结构化事实" in report.content
    assert "不能据此总结趋势、利润来源" in report.content
