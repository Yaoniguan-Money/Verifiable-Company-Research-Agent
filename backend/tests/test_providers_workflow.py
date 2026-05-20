from __future__ import annotations

from datetime import datetime, timezone

from app.db import session as db_session
from app.db.models import (
    EvidenceChunk,
    ExtractedFact,
    Report,
    ResearchTask,
    Source,
    VerificationResult,
)
from app.providers.llm import MockLLMProvider
from app.providers.search import MockSearchProvider
from app.schemas.chunk import EvidenceChunkRead
from app.schemas.common import ComplianceStatus
from app.schemas.report import ReportCreate
from app.services.research_workflow import ResearchWorkflowService
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession


def test_mock_search_provider_returns_sources() -> None:
    provider = MockSearchProvider()
    sources = provider.search("Sample Public Co", "Analyze R&D investment and operating risk")
    assert 2 <= len(sources) <= 3
    assert all(item.title for item in sources)
    assert all(item.raw_content for item in sources)
    assert all(item.title.startswith("[MOCK 演示占位]") for item in sources)
    assert all((item.url or "").startswith("mock://local/") for item in sources)
    assert all((item.source_metadata or {}).get("mock") is True for item in sources)
    assert all("不是联网搜索结果" in item.raw_content for item in sources)


def test_mock_llm_provider_returns_structured_facts() -> None:
    provider = MockLLMProvider()
    chunks = [
        EvidenceChunkRead(
            id="chunk_1",
            source_id="source_1",
            task_id="task_1",
            chunk_index=0,
            text="Public disclosure mentions sustained R&D investment growth.",
            metadata={"section": "r_and_d"},
            embedding_id="mock-emb-1",
            created_at=datetime.now(timezone.utc),
        )
    ]
    facts = provider.extract_facts(
        task_id="task_1",
        company_name="Sample Public Co",
        question="R&D change and operating risk",
        chunks=chunks,
    )
    assert len(facts) == 1
    assert facts[0].task_id == "task_1"
    assert facts[0].source_id == "source_1"
    assert facts[0].chunk_id == "chunk_1"
    assert 0 <= facts[0].confidence <= 1


def test_workflow_runs_to_report_and_persists(db: OrmSession) -> None:
    service = ResearchWorkflowService(db=db)
    task = service.create_research_task(
        company_name="Sample Public Co",
        question="Analyze R&D investment changes and potential operating risk",
    )
    outcome = service.run_workflow(task.id)
    assert outcome.success
    state = outcome.state
    assert state.status.value == "completed"
    assert state.task_id
    assert len(state.steps) >= 11
    assert state.steps[0].step_name == "load_task_node"
    assert "retrieve_evidence_node" in [step.step_name for step in state.steps]
    assert all(step.success for step in state.steps)

    task_id = state.task_id
    assert db.scalar(select(ResearchTask).where(ResearchTask.id == task_id)) is not None
    assert db.scalar(select(Source).where(Source.task_id == task_id)) is not None
    assert db.scalar(select(EvidenceChunk).where(EvidenceChunk.task_id == task_id)) is not None
    assert db.scalar(select(ExtractedFact).where(ExtractedFact.task_id == task_id)) is not None
    assert db.scalar(select(VerificationResult).where(VerificationResult.task_id == task_id)) is not None
    report = db.scalar(select(Report).where(Report.task_id == task_id))
    assert report is not None
    assert report.title
    assert report.content

    facts = db.scalars(select(ExtractedFact).where(ExtractedFact.task_id == task_id)).all()
    assert facts
    assert all(f.source_id and f.chunk_id for f in facts)
    assert all(0 <= f.confidence <= 1 for f in facts)

    verifications = db.scalars(
        select(VerificationResult).where(VerificationResult.task_id == task_id)
    ).all()
    assert verifications
    assert all(v.fact_id and v.task_id for v in verifications)
    assert all(v.reason for v in verifications)
    assert all(0 <= v.confidence <= 1 for v in verifications)
    # 3.E 接入后，不应默认全部 verified。
    assert any(getattr(v.status, "value", str(v.status)) != "verified" for v in verifications)


def test_report_citations_fields_are_complete(db: OrmSession) -> None:
    service = ResearchWorkflowService(db=db)
    task = service.create_research_task(company_name="Sample Public Co", question="Analyze public risk")
    service.run_workflow(task.id)
    report = service.get_report(task.id)
    assert report is not None
    assert len(report.citations) >= 1
    citation = report.citations[0]
    assert citation.source_id
    assert citation.chunk_id
    assert citation.url
    assert citation.title
    assert citation.retrieved_at


def test_report_uses_verification_status_sections(db: OrmSession) -> None:
    service = ResearchWorkflowService(db=db)
    task = service.create_research_task(company_name="Sample Public Co", question="验证状态分层")
    service.run_workflow(task.id)
    report = service.get_report(task.id)
    assert report is not None
    content = report.content
    assert "## 核心事实：能直接回答问题的内容" in content
    assert "## 可信度说明" in content
    assert "## 需要谨慎的地方" in content
    # 冲突与不足必须是审慎表达，不写成单一确定结论。
    verifications = service.list_verification_results(task.id)
    has_conflicted = any(getattr(v.status, "value", str(v.status)) == "conflicted" for v in verifications)
    has_insufficient = any(
        getattr(v.status, "value", str(v.status)) == "insufficient" for v in verifications
    )
    has_excluded = any(
        getattr(v.status, "value", str(v.status)) in {"outdated", "rejected"}
        for v in verifications
    )
    if has_conflicted:
        assert "不同来源说法不一致" in content
    if has_insufficient:
        assert "还需要更权威或第二个独立来源" in content
    if not has_conflicted and not has_insufficient and not has_excluded:
        assert "暂未发现需要单独提示的证据冲突" in content


def test_report_mainchain_includes_grounded_section(db: OrmSession) -> None:
    service = ResearchWorkflowService(db=db)
    task = service.create_research_task(company_name="Sample Public Co", question="研发投入与经营风险")
    result = service.run_workflow(task.id)
    assert result.success
    report = service.get_report(task.id)
    assert report is not None
    assert "## 证据摘录" in report.content
    assert "系统优先回看了这些来源片段" in report.content
    assert "《" in report.content


def test_workflow_degrades_when_llm_risk_analysis_fails(db: OrmSession) -> None:
    class FailingRiskLLM(MockLLMProvider):
        def analyze_risks(self, *args, **kwargs) -> str:
            raise RuntimeError("timeout")

    service = ResearchWorkflowService(db=db, llm_provider=FailingRiskLLM())
    task = service.create_research_task(company_name="Sample Public Co", question="研发投入与经营风险")
    result = service.run_workflow(task.id)

    assert result.success
    assert any(
        item.reason == "llm_risk_analysis_degraded"
        for item in result.state.workflow_decisions
    )
    report = service.get_report(task.id)
    assert report is not None
    assert "LLM 风险分析暂时不可用" in report.content
    assert "## 附录：处理记录" in report.content
    assert "LLM 风险分析" in report.content
    assert "规则摘要" in report.content


def test_generate_report_must_call_grounding_in_mainchain(db: OrmSession) -> None:
    service = ResearchWorkflowService(db=db)
    task = service.create_research_task(company_name="Sample Public Co", question="主链探针")
    result = service.run_workflow(task.id)
    assert result.success
    assert "retrieve_evidence_node" in [step.step_name for step in result.state.steps]
    assert "build_report_node" in [step.step_name for step in result.state.steps]
    report = service.get_report(task.id)
    assert report is not None
    assert "证据摘录" in report.content


def test_compliance_check_blocks_obvious_violation() -> None:
    provider = MockLLMProvider()
    result = provider.check_compliance("I recommend a buy here with a target_price of 100.")
    assert not result.is_compliant
    assert len(result.violations) >= 2
    assert "buy" in ",".join(result.violations)
    assert result.rewritten_text is not None
    assert result.status.value == "blocked"


def test_compliance_check_rewrites_return_prediction_phrase() -> None:
    provider = MockLLMProvider()
    result = provider.check_compliance("请给我 expected return 预测。")
    assert not result.is_compliant
    assert result.status.value == "rewritten"
    assert result.rewritten_text is not None


def test_report_output_layer_rewrites_target_price_phrase(db: OrmSession) -> None:
    class RewriteLLM(MockLLMProvider):
        def generate_report(self, *args, **kwargs) -> ReportCreate:
            base = super().generate_report(*args, **kwargs)
            return base.model_copy(
                update={"content": base.content + "\n\n附加：该公司 target_price 可进一步讨论。"}
            )

    service = ResearchWorkflowService(db=db, llm_provider=RewriteLLM())
    task = service.create_research_task(company_name="Rewrite Inc", question="请做公开信息分析")
    outcome = service.run_workflow(task.id)
    assert outcome.success
    report = service.get_report(task.id)
    assert report is not None
    assert report.compliance_status == ComplianceStatus.REWRITTEN
    assert "target_price" not in report.content
    assert "【已移除违规表达】" in report.content


def test_report_output_layer_blocks_buy_sell_advice(db: OrmSession) -> None:
    class BlockLLM(MockLLMProvider):
        def generate_report(self, *args, **kwargs) -> ReportCreate:
            base = super().generate_report(*args, **kwargs)
            return base.model_copy(update={"content": base.content + "\n\n附加：建议买入并继续加仓。"})

    service = ResearchWorkflowService(db=db, llm_provider=BlockLLM())
    task = service.create_research_task(company_name="Block Inc", question="请做公开信息分析")
    outcome = service.run_workflow(task.id)
    assert outcome.success
    report = service.get_report(task.id)
    assert report is not None
    assert report.compliance_status == ComplianceStatus.BLOCKED
    assert "建议买入" not in report.content
    assert "加仓" not in report.content
    assert "已按合规策略拒绝" in report.content


def test_claim_task_for_run_is_atomic(db: OrmSession) -> None:
    service = ResearchWorkflowService(db=db)
    task = service.create_research_task(company_name="Claim Test", question="Can only run once")

    db_other = db_session.SessionLocal()
    try:
        first = ResearchWorkflowService(db)._claim_task_for_run(task.id)
        second = ResearchWorkflowService(db_other)._claim_task_for_run(task.id)
        assert first is not None
        assert second is None
    finally:
        db_other.close()


def test_workflow_failure_cleans_partial_outputs_and_allows_retry(db: OrmSession) -> None:
    class FailingLLM(MockLLMProvider):
        def generate_report(self, *args, **kwargs) -> ReportCreate:
            raise RuntimeError("boom during report generation")

    service = ResearchWorkflowService(db=db, llm_provider=FailingLLM())
    task = service.create_research_task(company_name="Retry Inc", question="Trigger a failure")

    failed = service.run_workflow(task.id)
    assert not failed.success

    task_row = service.get_research_task(task.id)
    assert task_row is not None
    assert task_row.status == "failed"
    assert task_row.error_message == "boom during report generation"
    assert service.list_sources(task.id) == []
    assert service.list_extracted_facts(task.id) == []
    assert service.list_verification_results(task.id) == []
    assert service.get_report(task.id) is None

    recovered = ResearchWorkflowService(db=db).run_workflow(task.id)
    assert recovered.success
    assert recovered.state.status.value == "completed"
