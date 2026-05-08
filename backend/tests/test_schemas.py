"""阶段 1.B：Schema 单元测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.models.fact import ExtractedFact
from app.schemas.chunk import Citation, EvidenceChunkCreate
from app.schemas.common import (
    CONTENT_FETCH_STATUS_METADATA_KEY,
    SOURCE_LAYER_METADATA_KEY,
    ComplianceStatus,
    ContentFetchStatus,
    SourceAuthority,
    SourceLayer,
    TaskStatus,
    VerificationStatus,
    authority_label,
    blocks_high_confidence_fact,
    is_official_body_layer,
    source_layer_from_metadata,
    source_layer_priority,
)
from app.schemas.fact import ExtractedFactCreate, ExtractedFactExtractionOutput, ExtractedFactRead
from app.schemas.report import ReportRead
from app.schemas.task import ResearchTaskCreate
from app.schemas.verification import VerificationResultCreate
from app.schemas.workflow import WorkflowDecision, WorkflowState
from pydantic import ValidationError


def test_research_task_create_required_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchTaskCreate.model_validate({})

    obj = ResearchTaskCreate.model_validate(
        {
            "company_name": "样例股份",
            "question": "请分析近三年的研发投入变化",
        }
    )
    assert obj.company_name == "样例股份"
    assert obj.question.startswith("请分析")


def test_verification_status_enum_values() -> None:
    allowed = {item.value for item in VerificationStatus}
    assert allowed == {"verified", "conflicted", "insufficient", "outdated", "rejected"}


def test_source_quality_common_rules_are_centralized() -> None:
    metadata = {
        SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value,
        CONTENT_FETCH_STATUS_METADATA_KEY: ContentFetchStatus.FETCHED_CONTENT.value,
    }

    assert authority_label(0.9) == SourceAuthority.HIGH
    assert authority_label(0.46) == SourceAuthority.LOW
    assert source_layer_from_metadata(metadata) == SourceLayer.OFFICIAL_PDF
    assert is_official_body_layer(SourceLayer.OFFICIAL_DISCLOSURE_PAGE)
    assert source_layer_priority(SourceLayer.OFFICIAL_PDF) > source_layer_priority(SourceLayer.OFFICIAL_ENTRY_PAGE)
    assert blocks_high_confidence_fact(
        source_metadata={SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_ENTRY_PAGE.value},
        credibility_score=0.96,
    )
    assert blocks_high_confidence_fact(
        source_metadata={SOURCE_LAYER_METADATA_KEY: SourceLayer.THIRD_PARTY_BACKGROUND.value},
        credibility_score=0.46,
    )


def test_invalid_verification_status_should_fail() -> None:
    with pytest.raises(ValidationError):
        VerificationResultCreate.model_validate(
            {
                "fact_id": "fact_1",
                "task_id": "task_1",
                "status": "unknown_status",
                "confidence": 0.8,
                "supporting_sources": [],
                "conflicting_sources": [],
                "reason": "invalid",
            }
        )


def test_citation_has_source_and_chunk_binding() -> None:
    citation = Citation.model_validate(
        {
            "source_id": "source_1",
            "chunk_id": "chunk_1",
            "url": "https://example.com/report",
            "title": "2023 年度报告",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    assert citation.source_id == "source_1"
    assert citation.chunk_id == "chunk_1"


def test_report_schema_supports_citations_and_compliance_status() -> None:
    report = ReportRead.model_validate(
        {
            "id": "report_1",
            "task_id": "task_1",
            "title": "公司研究报告",
            "content": "基于公开资料的分析结果。",
            "citations": [
                {
                    "source_id": "source_1",
                    "chunk_id": "chunk_1",
                    "url": "https://example.com/report",
                    "title": "2023 年度报告",
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
            "compliance_status": "passed",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    assert report.citations[0].source_id == "source_1"
    assert report.citations[0].chunk_id == "chunk_1"
    assert report.compliance_status == ComplianceStatus.PASSED


def test_chunk_create_has_metadata_field() -> None:
    chunk = EvidenceChunkCreate.model_validate(
        {
            "source_id": "source_1",
            "task_id": "task_1",
            "chunk_index": 0,
            "text": "这是证据片段",
            "metadata": {"section": "研发投入"},
            "embedding_id": None,
        }
    )
    assert chunk.metadata is not None
    assert chunk.metadata["section"] == "研发投入"


def test_task_status_enum() -> None:
    assert TaskStatus.CREATED.value == "created"
    assert TaskStatus.RUNNING.value == "running"


def test_workflow_state_supports_structured_decisions() -> None:
    decision = WorkflowDecision(
        node="RecordVerificationRisk",
        reason="conflicted_facts",
        message="验证结果存在冲突",
        task_id="task_1",
        status_counts={"conflicted": 2},
    )
    state = WorkflowState(
        task_id="task_1",
        company_name="测试公司",
        question="测试问题",
        status=TaskStatus.RUNNING,
        workflow_decisions=[decision],
    )
    dumped = state.model_dump(mode="json")
    assert dumped["workflow_decisions"][0]["node"] == "RecordVerificationRisk"
    assert dumped["workflow_decisions"][0]["status_counts"]["conflicted"] == 2


def test_extracted_fact_create_valid_payload() -> None:
    fact = ExtractedFactCreate.model_validate(
        {
            "task_id": "task_1",
            "claim": "公司 2023 年研发投入同比增长",
            "metric_name": "R&D_expenditure",
            "value": "120 亿元",
            "period": "2023",
            "source_id": "source_1",
            "chunk_id": "chunk_1",
            "confidence": 0.82,
        }
    )
    assert fact.task_id == "task_1"
    assert fact.source_id == "source_1"
    assert fact.chunk_id == "chunk_1"
    # 可序列化，便于后续抽取服务输出。
    assert fact.model_dump(mode="json")["metric_name"] == "R&D_expenditure"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "task_id": "task_1",
            "claim": "缺少 source_id",
            "metric_name": "metric",
            "value": "1",
            "period": "2023",
            "chunk_id": "chunk_1",
            "confidence": 0.5,
        },
        {
            "task_id": "task_1",
            "claim": "缺少 chunk_id",
            "metric_name": "metric",
            "value": "1",
            "period": "2023",
            "source_id": "source_1",
            "confidence": 0.5,
        },
    ],
)
def test_extracted_fact_create_requires_source_and_chunk(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ExtractedFactCreate.model_validate(payload)


@pytest.mark.parametrize("bad_confidence", [-0.01, 1.01])
def test_extracted_fact_create_rejects_out_of_range_confidence(bad_confidence: float) -> None:
    with pytest.raises(ValidationError):
        ExtractedFactCreate.model_validate(
            {
                "task_id": "task_1",
                "claim": "置信度越界",
                "metric_name": "metric",
                "value": "1",
                "period": "2023",
                "source_id": "source_1",
                "chunk_id": "chunk_1",
                "confidence": bad_confidence,
            }
        )


def test_extracted_fact_read_supports_orm_model_validate() -> None:
    orm_fact = ExtractedFact(
        id="fact_1",
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        claim="公司 2023 年研发投入为 120 亿元",
        metric_name="R&D_expenditure",
        value="120 亿元",
        period="2023",
        confidence=0.91,
        created_at=datetime.now(timezone.utc),
    )
    read = ExtractedFactRead.model_validate(orm_fact)
    assert read.id == "fact_1"
    assert read.claim.startswith("公司 2023 年")
    assert read.source_id == "source_1"
    assert read.chunk_id == "chunk_1"


def test_extracted_fact_extraction_output_enforces_same_task_id() -> None:
    with pytest.raises(ValidationError):
        ExtractedFactExtractionOutput.model_validate(
            {
                "task_id": "task_main",
                "facts": [
                    {
                        "task_id": "task_other",
                        "claim": "任务不一致",
                        "metric_name": "metric",
                        "value": "1",
                        "period": "2023",
                        "source_id": "source_1",
                        "chunk_id": "chunk_1",
                        "confidence": 0.7,
                    }
                ],
            }
        )
