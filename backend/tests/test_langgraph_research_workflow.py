from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.core.config import Settings, get_settings
from app.providers.llm import MockLLMProvider
from app.providers.llm.base import ComplianceCheckResult
from app.providers.search import SearchProvider
from app.schemas.common import (
    SOURCE_LAYER_METADATA_KEY,
    ComplianceStatus,
    SourceLayer,
    SourceType,
    TaskStatus,
    source_layer_from_metadata,
)
from app.schemas.source import SourceCreate
from app.services.research_workflow import ResearchWorkflowService
from app.workflows.langgraph_research import (
    RESEARCH_GRAPH_NODE_NAMES,
    RESEARCH_GRAPH_REQUIRED_FIELDS,
    initial_research_graph_state,
)
from sqlalchemy.orm import Session


class _LowQualitySearchProvider(SearchProvider):
    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        return [
            SourceCreate(
                task_id="",
                title="Low quality blog",
                url="https://example.com/blog",
                source_type=SourceType.NEWS,
                retrieved_at=datetime.now(timezone.utc),
                raw_content="2024年营业收入为100亿元，研发费用为10亿元。",
                credibility_score=0.4,
                source_metadata={
                    SOURCE_LAYER_METADATA_KEY: SourceLayer.THIRD_PARTY_BACKGROUND.value
                },
            )
        ]


class _VerifiedSearchProvider(SearchProvider):
    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        now = datetime.now(timezone.utc)
        return [
            SourceCreate(
                task_id="",
                title="Annual Report A",
                url="https://example.com/a.pdf",
                source_type=SourceType.OFFICIAL_PDF,
                retrieved_at=now,
                raw_content="2024年营业收入为100亿元。该数据来自年度报告口径。",
                credibility_score=0.98,
                source_metadata={SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value},
            ),
            SourceCreate(
                task_id="",
                title="Annual Report B",
                url="https://example.com/b.pdf",
                source_type=SourceType.OFFICIAL_PDF,
                retrieved_at=now,
                raw_content="2024年营业收入为100亿元。该数据来自另一份公开披露。",
                credibility_score=0.98,
                source_metadata={SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value},
            ),
        ]


class _NoFactSearchProvider(SearchProvider):
    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        return [
            SourceCreate(
                task_id="",
                title="No numeric disclosure",
                url="https://example.com/no-facts",
                source_type=SourceType.OTHER,
                retrieved_at=datetime.now(timezone.utc),
                raw_content=(
                    "这是一段公开资料说明，只描述企业文化、品牌定位和一般性经营环境，"
                    "不包含可抽取的金额、产量、收入、研发费用或年份指标。"
                ),
                credibility_score=0.7,
            )
        ]


def test_research_graph_state_has_required_fields() -> None:
    state = initial_research_graph_state("task_1")

    assert set(RESEARCH_GRAPH_REQUIRED_FIELDS) <= set(state)
    assert state["status"] == "running"
    assert state["sources"] == []
    assert state["workflow_decisions"] == []


def test_langgraph_graph_can_compile(db: Session) -> None:
    service = ResearchWorkflowService(db)
    task = service.create_research_task(company_name="Compile Inc", question="研究问题")

    result = service.run_workflow(task.id)

    assert result.success is True
    assert result.state.status == TaskStatus.COMPLETED
    assert "load_task_node" in [item.step_name for item in result.state.steps]
    assert "compliance_check_node" in RESEARCH_GRAPH_NODE_NAMES


def test_default_workflow_engine_is_langgraph() -> None:
    assert Settings(_env_file=None).workflow_engine == "langgraph"


def test_langgraph_workflow_runs_graph_nodes_by_default(db: Session, monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOW_ENGINE", "langgraph")
    get_settings.cache_clear()

    service = ResearchWorkflowService(db)
    task = service.create_research_task(
        company_name="Demo Tech Inc",
        question="What changed in R&D spending and key operating risks?",
    )

    result = service.run_workflow(task.id)
    step_names = [item.step_name for item in result.state.steps]

    assert result.success is True
    assert result.state.status == TaskStatus.COMPLETED
    assert step_names[:7] == [
        "load_task_node",
        "collect_sources_node",
        "source_quality_gate_node",
        "ingest_chunks_node",
        "embed_chunks_node",
        "retrieve_evidence_node",
        "extract_facts_node",
    ]
    assert "build_report_node" in step_names
    assert "compliance_check_node" in step_names
    assert step_names[-1] in {"persist_result_node", "persist_blocked_result_node"}
    assert all(item.success for item in result.state.steps)
    assert result.report_id is not None

    monkeypatch.delenv("WORKFLOW_ENGINE", raising=False)
    get_settings.cache_clear()


def test_service_engine_legacy_fallback_still_runs(db: Session, monkeypatch) -> None:
    monkeypatch.setenv("WORKFLOW_ENGINE", "service")
    get_settings.cache_clear()

    service = ResearchWorkflowService(db)
    task = service.create_research_task(company_name="Legacy Inc", question="研究问题")

    result = service.run_workflow(task.id)

    assert result.success is True
    assert result.state.status == TaskStatus.COMPLETED
    assert "ChunkAndIndexSources" in [item.step_name for item in result.state.steps]

    monkeypatch.delenv("WORKFLOW_ENGINE", raising=False)
    get_settings.cache_clear()


def test_source_quality_insufficient_branch_records_decision(
    db: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKFLOW_ENGINE", "langgraph")
    get_settings.cache_clear()

    service = ResearchWorkflowService(db, search_provider=_LowQualitySearchProvider())
    task = service.create_research_task(company_name="Low Quality Inc", question="收入和研发")

    result = service.run_workflow(task.id)
    step_names = [item.step_name for item in result.state.steps]

    assert result.success is True
    assert "record_source_quality_gap_node" in step_names
    assert any(
        item.reason == "source_quality_insufficient"
        for item in result.state.workflow_decisions
    )
    report = service.get_report(task.id)
    assert report is not None
    assert "来源质量摘要" in report.content

    monkeypatch.delenv("WORKFLOW_ENGINE", raising=False)
    get_settings.cache_clear()


def test_langgraph_skips_verification_risk_when_facts_are_verified(
    db: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKFLOW_ENGINE", "langgraph")
    get_settings.cache_clear()

    service = ResearchWorkflowService(db, search_provider=_VerifiedSearchProvider())
    task = service.create_research_task(
        company_name="Verified Inc",
        question="近三年收入变化",
    )

    result = service.run_workflow(task.id)
    step_names = [item.step_name for item in result.state.steps]

    assert result.success is True
    assert "verify_facts_node" in step_names
    assert "record_verification_risk_node" not in step_names
    assert service.list_verification_results(task.id)

    monkeypatch.delenv("WORKFLOW_ENGINE", raising=False)
    get_settings.cache_clear()


def test_langgraph_routes_no_fact_case_to_evidence_gap(
    db: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("WORKFLOW_ENGINE", "langgraph")
    get_settings.cache_clear()

    service = ResearchWorkflowService(db, search_provider=_NoFactSearchProvider())
    task = service.create_research_task(
        company_name="No Fact Inc",
        question="近三年研发投入变化",
    )

    result = service.run_workflow(task.id)
    step_names = [item.step_name for item in result.state.steps]

    assert result.success is True
    assert result.state.status == TaskStatus.COMPLETED
    assert "record_evidence_gap_node" in step_names
    assert "verify_facts_node" not in step_names
    assert any(item.reason == "no_extracted_facts" for item in result.state.workflow_decisions)
    assert service.list_extracted_facts(task.id) == []
    assert service.list_verification_results(task.id) == []

    monkeypatch.delenv("WORKFLOW_ENGINE", raising=False)
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("status", "expected_step", "expected_report_status"),
    [
        (ComplianceStatus.PASSED, "persist_result_node", "passed"),
        (ComplianceStatus.REWRITTEN, "apply_compliance_rewrite_node", "rewritten"),
        (ComplianceStatus.BLOCKED, "persist_blocked_result_node", "blocked"),
    ],
)
def test_compliance_action_branches(
    db: Session,
    monkeypatch,
    status: ComplianceStatus,
    expected_step: str,
    expected_report_status: str,
) -> None:
    class BranchingComplianceLLM(MockLLMProvider):
        def check_compliance(self, text: str) -> ComplianceCheckResult:
            return ComplianceCheckResult(
                is_compliant=status == ComplianceStatus.PASSED,
                status=status,
                violations=["branch_test"] if status != ComplianceStatus.PASSED else [],
                rewritten_text="合规改写后的报告" if status != ComplianceStatus.PASSED else None,
                checked_at=datetime.now(timezone.utc),
            )

    monkeypatch.setenv("WORKFLOW_ENGINE", "langgraph")
    get_settings.cache_clear()

    service = ResearchWorkflowService(db, llm_provider=BranchingComplianceLLM())
    task = service.create_research_task(company_name="Compliance Inc", question="研究问题")

    result = service.run_workflow(task.id)
    step_names = [item.step_name for item in result.state.steps]
    report = service.get_report(task.id)

    assert result.success is True
    assert expected_step in step_names
    assert report is not None
    assert report.compliance_status.value == expected_report_status

    monkeypatch.delenv("WORKFLOW_ENGINE", raising=False)
    get_settings.cache_clear()


def test_non_mock_provider_configuration_does_not_fallback_to_mock(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    get_settings.cache_clear()

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY is required"):
        ResearchWorkflowService(db=object())  # type: ignore[arg-type]

    monkeypatch.setenv("LLM_PROVIDER", "mock")
    get_settings.cache_clear()


def test_official_pdf_citation_sorts_above_entry_page_and_low_authority(
    db: Session,
    monkeypatch,
) -> None:
    class MixedQualityProvider(SearchProvider):
        def search(self, company_name: str, question: str) -> list[SourceCreate]:
            now = datetime.now(timezone.utc)
            return [
                SourceCreate(
                    task_id="",
                    title="Official entry page",
                    url="https://example.com/ir",
                    source_type=SourceType.OFFICIAL_WEBSITE,
                    retrieved_at=now,
                    raw_content="2024年营业收入为100亿元。",
                    credibility_score=0.96,
                    source_metadata={
                        SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_ENTRY_PAGE.value
                    },
                ),
                SourceCreate(
                    task_id="",
                    title="Official PDF",
                    url="https://example.com/report.pdf",
                    source_type=SourceType.OFFICIAL_PDF,
                    retrieved_at=now,
                    raw_content="2024年营业收入为100亿元。",
                    credibility_score=0.98,
                    source_metadata={SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value},
                ),
                SourceCreate(
                    task_id="",
                    title="Low authority note",
                    url="https://example.com/forum",
                    source_type=SourceType.NEWS,
                    retrieved_at=now,
                    raw_content="2024年营业收入为100亿元。",
                    credibility_score=0.4,
                    source_metadata={
                        SOURCE_LAYER_METADATA_KEY: SourceLayer.THIRD_PARTY_BACKGROUND.value
                    },
                ),
            ]

    monkeypatch.setenv("WORKFLOW_ENGINE", "langgraph")
    get_settings.cache_clear()

    service = ResearchWorkflowService(db, search_provider=MixedQualityProvider())
    task = service.create_research_task(company_name="Mixed Inc", question="收入")

    result = service.run_workflow(task.id)
    report = service.get_report(task.id)
    source_map = {item.id: item for item in service.list_sources(task.id)}

    assert result.success is True
    assert report is not None
    assert report.citations
    first_source = source_map[report.citations[0].source_id]
    assert source_layer_from_metadata(first_source.source_metadata) == SourceLayer.OFFICIAL_PDF

    monkeypatch.delenv("WORKFLOW_ENGINE", raising=False)
    get_settings.cache_clear()
