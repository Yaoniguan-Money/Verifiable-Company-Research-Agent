"""阶段 3.B：FactExtractionService 测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.schemas.chunk import EvidenceChunkRead
from app.schemas.common import (
    SOURCE_CREDIBILITY_SCORE_METADATA_KEY,
    SOURCE_LAYER_METADATA_KEY,
    SOURCE_METADATA_KEY,
    SourceLayer,
)
from app.schemas.retrieval import RetrievedEvidence
from app.services.fact_extraction import FactExtractionService


def test_extract_single_chunk_to_structured_fact() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="公司披露2023年研发投入为100亿元。",
        metadata={"section": "研发"},
        embedding_id="emb_1",
        created_at=datetime.now(timezone.utc),
    )
    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="研发投入变化",
        chunks=[chunk],
    )
    assert len(out.facts) == 1
    fact = out.facts[0]
    assert fact.task_id == "task_1"
    assert fact.source_id == "source_1"
    assert fact.chunk_id == "chunk_1"
    assert fact.metric_name == "R&D_expenditure"
    assert fact.value == "100亿元"
    assert fact.period == "2023"
    assert 0.0 <= fact.confidence <= 1.0


def test_fact_extraction_skips_percentage_values_for_monetary_metrics() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="公司披露2024年研发投入占营业收入比例为1.02%，营业收入同比增长5.5%。",
        metadata={"section": "财务"},
        embedding_id="emb_1",
        created_at=datetime.now(timezone.utc),
    )

    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="研发投入和收入",
        chunks=[chunk],
    )

    assert out.facts == []


def test_official_entry_page_chunk_does_not_enter_high_confidence_fact_extraction() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="官方入口页面提到2024年营收为100亿元。",
        metadata={
            SOURCE_CREDIBILITY_SCORE_METADATA_KEY: 0.96,
            SOURCE_METADATA_KEY: {SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_ENTRY_PAGE.value},
        },
        embedding_id="emb_1",
        created_at=datetime.now(timezone.utc),
    )

    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="营收",
        chunks=[chunk],
    )

    assert out.facts == []


def test_low_authority_chunk_does_not_enter_high_confidence_fact_extraction() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="第三方讨论称2024年营收为100亿元。",
        metadata={
            SOURCE_CREDIBILITY_SCORE_METADATA_KEY: 0.46,
            SOURCE_METADATA_KEY: {SOURCE_LAYER_METADATA_KEY: SourceLayer.THIRD_PARTY_BACKGROUND.value},
        },
        embedding_id="emb_1",
        created_at=datetime.now(timezone.utc),
    )

    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="营收",
        chunks=[chunk],
    )

    assert out.facts == []


def test_extract_multiple_chunks_multiple_facts() -> None:
    svc = FactExtractionService()
    chunks = [
        EvidenceChunkRead(
            id="chunk_1",
            source_id="source_1",
            task_id="task_1",
            chunk_index=0,
            text="2022年营收为500亿元。",
            metadata=None,
            embedding_id=None,
            created_at=datetime.now(timezone.utc),
        ),
        EvidenceChunkRead(
            id="chunk_2",
            source_id="source_2",
            task_id="task_1",
            chunk_index=1,
            text="2021年净利润为20亿元。",
            metadata=None,
            embedding_id=None,
            created_at=datetime.now(timezone.utc),
        ),
    ]
    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="营收与利润",
        chunks=chunks,
    )
    assert len(out.facts) == 2
    assert {f.metric_name for f in out.facts} == {"revenue", "net_profit"}
    assert {f.source_id for f in out.facts} == {"source_1", "source_2"}
    assert {f.chunk_id for f in out.facts} == {"chunk_1", "chunk_2"}


def test_extract_multiple_periods_in_dense_chunk() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="2022年研发投入为80亿元，2023年研发投入为100亿元；2023年营收为500亿元。",
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )

    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="研发投入与营收",
        chunks=[chunk],
    )

    by_metric_value = {(f.metric_name, f.value): f.period for f in out.facts}
    assert by_metric_value[("R&D_expenditure", "80亿元")] == "2022"
    assert by_metric_value[("R&D_expenditure", "100亿元")] == "2023"
    assert by_metric_value[("revenue", "500亿元")] == "2023"


def test_extract_common_financial_report_metric_aliases() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="2024年营业总收入411.87亿元，归母净利润51.53亿元，研发费用3.14亿元。",
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )

    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="财务表现",
        chunks=[chunk],
    )

    assert {(f.metric_name, f.value) for f in out.facts} == {
        ("revenue", "411.87亿元"),
        ("net_profit_parent", "51.53亿元"),
        ("R&D_expenditure", "3.14亿元"),
    }


def test_extract_rd_amount_from_news_style_phrasing() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="2024年，样例股份研发投入超200亿元；2025年半年报显示研发投入309亿元。",
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )

    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="样例股份",
        question="研发投入",
        chunks=[chunk],
    )

    rd_values = {(fact.period, fact.value) for fact in out.facts if fact.metric_name == "R&D_expenditure"}
    assert ("2024", "200亿元") in rd_values
    assert ("2025", "309亿元") in rd_values


def test_unknown_period_claim_uses_readable_label() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="本报告期末，归母净利润51.53亿元。",
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )

    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="利润",
        chunks=[chunk],
    )

    assert out.facts[0].period == "unknown_period"
    assert out.facts[0].claim == "期间未识别：归母净利润为51.53亿元"


def test_known_period_fact_replaces_unknown_period_duplicate() -> None:
    svc = FactExtractionService()
    evidences = [
        RetrievedEvidence(
            chunk_id="chunk_1",
            source_id="source_1",
            task_id="task_1",
            text="研发投入为542亿元。",
            score=0.7,
            source_title="来源A",
            source_url=None,
            source_type="annual_report",
            retrieved_at=datetime.now(timezone.utc),
            metadata=None,
        ),
        RetrievedEvidence(
            chunk_id="chunk_2",
            source_id="source_1",
            task_id="task_1",
            text="2024年研发投入为542亿元。",
            score=0.7,
            source_title="来源A",
            source_url=None,
            source_type="annual_report",
            retrieved_at=datetime.now(timezone.utc),
            metadata=None,
        ),
    ]

    out = svc.extract_from_retrieved_evidences(
        task_id="task_1",
        company_name="样例股份",
        question="研发投入",
        evidences=evidences,
    )

    assert [(item.period, item.value) for item in out.facts] == [("2024", "542亿元")]


def test_extracts_financial_table_rows_with_year_headers() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_table",
        source_id="source_table",
        task_id="task_1",
        chunk_index=0,
        text="\n".join(
            [
                "项目 2024年 2023年 2022年",
                "研发费用 542亿元 399亿元 202亿元",
                "汽车相关产品收入 6171.48亿元 4834.53亿元 3246.91亿元",
                "乘用车产能 4,479,392辆 3,800,000辆 3,100,000辆",
                "乘用车产量 4,479,392辆 3,750,000辆 3,000,000辆",
                "乘用车销量 4,545,423辆 3,820,000辆 3,050,000辆",
            ]
        ),
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )

    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="样例股份",
        question="研发投入、收入结构和产能产量",
        chunks=[chunk],
    )

    facts = {(item.metric_name, item.period, item.value) for item in out.facts}
    assert ("R&D_expenditure", "2024", "542亿元") in facts
    assert ("R&D_expenditure", "2023", "399亿元") in facts
    assert ("revenue_segment:汽车相关产品", "2024", "6171.48亿元") in facts
    assert ("production_capacity:乘用车", "2024", "4479392辆") in facts
    assert ("production_volume:乘用车", "2024", "4479392辆") in facts
    assert ("sales_volume:乘用车", "2024", "4545423辆") in facts


def test_extract_from_retrieved_evidence() -> None:
    svc = FactExtractionService()
    ev = RetrievedEvidence(
        chunk_id="chunk_9",
        source_id="source_9",
        task_id="task_9",
        text="2023年研发投入为88亿元。",
        score=0.88,
        source_title="年度报告",
        source_url="https://example.com",
        source_type="annual_report",
        retrieved_at=datetime.now(timezone.utc),
        metadata={"k": 1},
    )
    out = svc.extract_from_retrieved_evidences(
        task_id="task_9",
        company_name="公司A",
        question="研发",
        evidences=[ev],
    )
    assert len(out.facts) == 1
    assert out.facts[0].chunk_id == "chunk_9"
    assert out.facts[0].source_id == "source_9"


def test_no_extractable_fact_returns_empty_list() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_1",
        source_id="source_1",
        task_id="task_1",
        chunk_index=0,
        text="该段仅描述战略方向，没有可量化指标。",
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )
    out = svc.extract_from_chunks(
        task_id="task_1",
        company_name="测试公司",
        question="经营情况",
        chunks=[chunk],
    )
    assert out.facts == []


def test_missing_source_or_chunk_id_should_skip_untraceable_fact() -> None:
    svc = FactExtractionService()
    out = svc.extract_from_retrieved_evidences(
        task_id="task_1",
        company_name="测试公司",
        question="研发",
        evidences=[
            RetrievedEvidence(
                chunk_id="chunk_1",
                source_id="",
                task_id="task_1",
                text="2023年研发投入为100亿元。",
                score=0.6,
                source_title="来源A",
                source_url=None,
                source_type="announcement",
                retrieved_at=datetime.now(timezone.utc),
                metadata=None,
            ),
            RetrievedEvidence(
                chunk_id="",
                source_id="source_1",
                task_id="task_1",
                text="2023年研发投入为100亿元。",
                score=0.6,
                source_title="来源B",
                source_url=None,
                source_type="announcement",
                retrieved_at=datetime.now(timezone.utc),
                metadata=None,
            ),
        ],
    )
    assert out.facts == []


def test_cross_task_chunk_should_raise_error() -> None:
    svc = FactExtractionService()
    chunk = EvidenceChunkRead(
        id="chunk_x",
        source_id="source_x",
        task_id="task_other",
        chunk_index=0,
        text="2023年研发投入为100亿元。",
        metadata=None,
        embedding_id=None,
        created_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ValueError, match="task_id 不一致"):
        svc.extract_from_chunks(
            task_id="task_1",
            company_name="测试公司",
            question="研发投入",
            chunks=[chunk],
        )


def test_cross_task_evidence_should_raise_error() -> None:
    svc = FactExtractionService()
    ev = RetrievedEvidence(
        chunk_id="chunk_y",
        source_id="source_y",
        task_id="task_other",
        text="2022年营收为500亿元。",
        score=0.9,
        source_title="来源",
        source_url=None,
        source_type="announcement",
        retrieved_at=datetime.now(timezone.utc),
        metadata=None,
    )
    with pytest.raises(ValueError, match="task_id 不一致"):
        svc.extract_from_retrieved_evidences(
            task_id="task_1",
            company_name="测试公司",
            question="营收",
            evidences=[ev],
        )

