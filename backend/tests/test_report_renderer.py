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
    assert "## 附录" in report.content
    assert "来源或期间过旧" in report.content or "old fact" in report.content
    assert "old fact" in report.content
    assert "已排除" in report.content
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

    assert "## 附录" in report.content
    assert "没有抽取到" in report.content and "研发" in report.content


def test_mock_report_renderer_includes_material_confidence_section() -> None:
    now = datetime.now(timezone.utc)
    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task(),
            verified_facts=[_fact(fact_id="ok", claim="2024年营业收入为100亿元")],
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

    assert "## 附录" in report.content
    assert "已采信" in report.content
    assert "unit_normalized_match" not in report.content


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

    assert "## 核心发现" in report.content
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

    assert "只展示前 4 条冲突条目" in report.content or "冲突" in report.content
    assert "仅来自单一路径" not in report.content
    assert "待核实" not in report.content


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

    assert "尚未抽出" in report.content or "没有抽取到" in report.content


def test_report_renderer_keeps_fact_source_numbers_aligned_after_url_dedupe() -> None:
    now = datetime.now(timezone.utc)
    first = _fact(fact_id="one", claim="第一条事实")
    second = _fact(fact_id="two", claim="第二条事实")

    report = MockReportRenderer().render(
        ReportRenderInput(
            task=_task(),
            core_facts=[first, second],
            citations=[
                Citation(
                    source_id=first.source_id,
                    chunk_id=first.chunk_id,
                    url="https://example.com/report.pdf",
                    title="样例年报",
                    retrieved_at=now,
                ),
                Citation(
                    source_id=second.source_id,
                    chunk_id=second.chunk_id,
                    url="https://example.com/report.pdf",
                    title="样例年报重复块",
                    retrieved_at=now,
                ),
            ],
        )
    )

    assert report.content.count("https://example.com/report.pdf") == 1
    assert "- 第三条事实" not in report.content
    assert "- 第一条事实（来源 1）" in report.content
    assert "- 第二条事实（来源 1）" in report.content
    assert "来源 2" not in report.content
