"""阶段 2.E：Report grounding / citation 强化测试。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.db.init_db import get_default_user
from app.db.models import EvidenceChunk, ExtractedFact, ResearchTask, Source
from app.db.models.source import SourceType
from app.schemas.chunk import Citation
from app.schemas.common import (
    CONTENT_FETCH_STATUS_METADATA_KEY,
    SOURCE_CREDIBILITY_SCORE_METADATA_KEY,
    SOURCE_LAYER_METADATA_KEY,
    SOURCE_METADATA_KEY,
    ContentFetchStatus,
    SourceLayer,
)
from app.schemas.retrieval import RetrievedEvidence
from app.services.report_evidence import ReportEvidenceService
from app.services.report_grounding import ReportGroundingService
from sqlalchemy.orm import Session as OrmSession


def _seed_one(db: OrmSession) -> tuple[ResearchTask, Source, EvidenceChunk]:
    u = get_default_user(db)
    task = ResearchTask(user_id=u.id, company_name="GroundingCo", question="风险是什么？")
    db.add(task)
    db.commit()
    db.refresh(task)

    src = Source(
        task_id=task.id,
        title="Grounding 来源",
        url="https://example.com/grounding",
        source_type=SourceType.NEWS,
        published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime.now(timezone.utc),
        raw_content="公司公开资料显示，供应链与成本波动是近期风险点。",
    )
    db.add(src)
    db.commit()
    db.refresh(src)

    ch = EvidenceChunk(
        source_id=src.id,
        task_id=task.id,
        chunk_index=0,
        text="供应链与成本波动是近期风险点。",
        chunk_metadata={"tag": "risk"},
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return task, src, ch


def test_retrieved_evidence_can_format_to_citation(db: OrmSession) -> None:
    task, src, ch = _seed_one(db)
    ev = RetrievedEvidence(
        chunk_id=ch.id,
        source_id=src.id,
        task_id=task.id,
        text=ch.text,
        score=0.91,
        source_title=src.title,
        source_url=src.url,
        source_type=str(src.source_type),
        retrieved_at=src.retrieved_at,
        metadata=ch.chunk_metadata,
    )
    service = ReportGroundingService()
    cits = service.format_citations([ev])
    assert len(cits) == 1
    c = cits[0]
    assert c.source_id == src.id
    assert c.chunk_id == ch.id
    assert c.title == src.title
    assert c.url == src.url
    assert c.retrieved_at == src.retrieved_at


def test_grounded_section_contains_citation_and_traceable_ids(db: OrmSession) -> None:
    task, src, ch = _seed_one(db)
    ev = RetrievedEvidence(
        chunk_id=ch.id,
        source_id=src.id,
        task_id=task.id,
        text=ch.text,
        score=0.88,
        source_title=src.title,
        source_url=src.url,
        source_type=str(src.source_type),
        retrieved_at=src.retrieved_at,
        metadata=ch.chunk_metadata,
    )
    section = ReportGroundingService().build_grounded_section(
        query="近期经营风险",
        evidences=[ev],
        max_items=2,
    )
    assert "《" in section.content
    assert "score=" not in section.content
    assert len(section.citations) == 1
    cit = section.citations[0]

    # citation integrity：必须能回查到真实 chunk 与 source
    db_chunk = db.get(EvidenceChunk, cit.chunk_id)
    assert db_chunk is not None
    db_source = db.get(Source, cit.source_id)
    assert db_source is not None


def test_grounded_section_prioritizes_high_authority_evidence() -> None:
    now = datetime.now(timezone.utc)
    low = RetrievedEvidence(
        chunk_id="low_chunk",
        source_id="low_source",
        task_id="task",
        text="低可信来源提到经营风险。",
        score=0.99,
        source_title="低可信来源",
        source_url="https://xueqiu.com/123",
        source_type="news",
        retrieved_at=now,
        metadata={
            SOURCE_CREDIBILITY_SCORE_METADATA_KEY: 0.46,
            SOURCE_METADATA_KEY: {SOURCE_LAYER_METADATA_KEY: SourceLayer.THIRD_PARTY_BACKGROUND.value},
        },
    )
    high = RetrievedEvidence(
        chunk_id="high_chunk",
        source_id="high_source",
        task_id="task",
        text="官方 PDF 披露了公告、年报、半年报和监管披露。",
        score=0.50,
        source_title="样例公开公司年度报告官方 PDF",
        source_url="https://ir.mi.com/report.pdf",
        source_type=SourceLayer.OFFICIAL_PDF.value,
        retrieved_at=now,
        metadata={
            SOURCE_CREDIBILITY_SCORE_METADATA_KEY: 0.96,
            SOURCE_METADATA_KEY: {SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value},
        },
    )

    section = ReportGroundingService().build_grounded_section(
        query="优先使用权威来源",
        evidences=[low, high],
        max_items=1,
    )

    assert section.citations[0].source_id == "high_source"
    assert "样例公开公司年度报告官方 PDF" in section.content


def test_no_evidence_returns_insufficient_and_no_fake_citation() -> None:
    section = ReportGroundingService().build_grounded_section(
        query="没有命中",
        evidences=[],
    )
    assert "证据不足" in section.content
    assert section.citations == []


def test_report_citation_merge_keeps_distinct_chunks_per_source() -> None:
    retrieved_at = datetime.now(timezone.utc)
    service = ReportEvidenceService.__new__(ReportEvidenceService)

    citations = service._merge_citations(
        [
            Citation(
                source_id="source_1",
                chunk_id="chunk_1",
                url="https://example.com/report",
                title="Annual report",
                retrieved_at=retrieved_at,
            )
        ],
        [
            Citation(
                source_id="source_1",
                chunk_id="chunk_2",
                url="https://example.com/report",
                title="Annual report",
                retrieved_at=retrieved_at,
            ),
            Citation(
                source_id="source_1",
                chunk_id="chunk_1",
                url="https://example.com/report",
                title="Annual report",
                retrieved_at=retrieved_at,
            ),
        ],
    )

    assert [(item.source_id, item.chunk_id) for item in citations] == [
        ("source_1", "chunk_1"),
        ("source_1", "chunk_2"),
    ]


def test_fact_citation_merge_keeps_same_source_distinct_chunks(db: OrmSession) -> None:
    task, src, first_chunk = _seed_one(db)
    second_chunk = EvidenceChunk(
        source_id=src.id,
        task_id=task.id,
        chunk_index=1,
        text="second chunk keeps traceable evidence",
        chunk_metadata={"tag": "second"},
    )
    db.add(second_chunk)
    db.flush()
    db.add_all(
        [
            ExtractedFact(
                task_id=task.id,
                source_id=src.id,
                chunk_id=first_chunk.id,
                claim="first chunk claim",
                metric_name="revenue",
                value="100",
                period="2024",
                confidence=0.8,
            ),
            ExtractedFact(
                task_id=task.id,
                source_id=src.id,
                chunk_id=second_chunk.id,
                claim="second chunk claim",
                metric_name="profit",
                value="20",
                period="2024",
                confidence=0.8,
            ),
        ]
    )
    db.commit()

    citations = ReportEvidenceService(db).merge_with_fact_citations(task.id, [])

    assert [(item.source_id, item.chunk_id) for item in citations] == [
        (src.id, first_chunk.id),
        (src.id, second_chunk.id),
    ]


def test_report_source_quality_summary_counts_official_body_and_entry(db: OrmSession) -> None:
    u = get_default_user(db)
    task = ResearchTask(user_id=u.id, company_name="样例公开公司", question="来源质量")
    db.add(task)
    db.flush()
    db.add_all(
        [
            Source(
                task_id=task.id,
                title="样例公开公司年度报告官方 PDF",
                url="https://ir.mi.com/report.pdf",
                source_type=SourceType.OFFICIAL_PDF,
                retrieved_at=datetime.now(timezone.utc),
                raw_content="官方 PDF 正文",
                credibility_score=0.98,
                source_metadata={
                    SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value,
                    CONTENT_FETCH_STATUS_METADATA_KEY: ContentFetchStatus.FETCHED_CONTENT.value,
                },
            ),
            Source(
                task_id=task.id,
                title="港交所披露易入口",
                url="https://www.hkexnews.hk/",
                source_type=SourceType.ANNOUNCEMENT,
                retrieved_at=datetime.now(timezone.utc),
                raw_content="content_fetch_status=entry_page_only",
                credibility_score=0.96,
                source_metadata={
                    SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_ENTRY_PAGE.value,
                    CONTENT_FETCH_STATUS_METADATA_KEY: ContentFetchStatus.ENTRY_PAGE_ONLY.value,
                },
            ),
            Source(
                task_id=task.id,
                title="雪球讨论",
                url="https://xueqiu.com/123",
                source_type=SourceType.NEWS,
                retrieved_at=datetime.now(timezone.utc),
                raw_content="第三方讨论",
                credibility_score=0.46,
                source_metadata={SOURCE_LAYER_METADATA_KEY: SourceLayer.THIRD_PARTY_BACKGROUND.value},
            ),
        ]
    )
    db.commit()

    summary = ReportEvidenceService(db).build_source_quality_summary(task.id)

    assert "- 官方/监管/交易所正文：1 条。" in summary
    assert "- 官方入口但不是正文：1 条。" in summary
    assert "- 第三方背景材料：1 条。" in summary
    assert "- 低可信来源：1 条。" in summary


def test_report_citations_sort_official_pdf_before_low_authority(db: OrmSession) -> None:
    u = get_default_user(db)
    task = ResearchTask(user_id=u.id, company_name="样例公开公司", question="citation 排序")
    db.add(task)
    db.flush()
    low = Source(
        task_id=task.id,
        title="雪球讨论",
        url="https://xueqiu.com/123",
        source_type=SourceType.NEWS,
        retrieved_at=datetime.now(timezone.utc),
        raw_content="第三方讨论",
        credibility_score=0.46,
        source_metadata={SOURCE_LAYER_METADATA_KEY: SourceLayer.THIRD_PARTY_BACKGROUND.value},
    )
    official = Source(
        task_id=task.id,
        title="样例公开公司年度报告官方 PDF",
        url="https://ir.mi.com/report.pdf",
        source_type=SourceType.OFFICIAL_PDF,
        retrieved_at=datetime.now(timezone.utc),
        raw_content="官方 PDF 正文",
        credibility_score=0.98,
        source_metadata={
            SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value,
            CONTENT_FETCH_STATUS_METADATA_KEY: ContentFetchStatus.FETCHED_CONTENT.value,
        },
    )
    db.add_all([low, official])
    db.commit()

    retrieved_at = datetime.now(timezone.utc)
    citations = ReportEvidenceService(db)._sort_citations_by_source_quality(
        task.id,
        [
            Citation(source_id=low.id, chunk_id="low", url=low.url, title=low.title, retrieved_at=retrieved_at),
            Citation(
                source_id=official.id,
                chunk_id="official",
                url=official.url,
                title=official.title,
                retrieved_at=retrieved_at,
            ),
        ],
    )

    assert citations[0].source_id == official.id


def test_report_evidence_includes_official_pdf_chunk_even_if_retrieval_misses_it(
    db: OrmSession,
) -> None:
    u = get_default_user(db)
    task = ResearchTask(user_id=u.id, company_name="样例公开公司", question="经营风险")
    db.add(task)
    db.flush()
    source = Source(
        task_id=task.id,
        title="样例公开公司年度报告官方 PDF",
        url="https://ir.mi.com/report.pdf",
        source_type=SourceType.OFFICIAL_PDF,
        retrieved_at=datetime.now(timezone.utc),
        raw_content="Annual report official disclosure text",
        credibility_score=0.98,
        source_metadata={
            SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value,
            CONTENT_FETCH_STATUS_METADATA_KEY: ContentFetchStatus.FETCHED_CONTENT.value,
        },
    )
    db.add(source)
    db.flush()
    chunk = EvidenceChunk(
        source_id=source.id,
        task_id=task.id,
        chunk_index=0,
        text="Annual report official disclosure text",
        chunk_metadata={},
    )
    db.add(chunk)
    db.commit()

    service = ReportEvidenceService(db)
    evidences = service._include_official_body_evidence(task.id, [])

    assert len(evidences) == 1
    assert evidences[0].source_id == source.id
    assert evidences[0].metadata is not None
    assert evidences[0].metadata[SOURCE_METADATA_KEY][SOURCE_LAYER_METADATA_KEY] == SourceLayer.OFFICIAL_PDF.value


def test_grounded_section_avoids_forbidden_terms(db: OrmSession) -> None:
    task, src, ch = _seed_one(db)
    ev = RetrievedEvidence(
        chunk_id=ch.id,
        source_id=src.id,
        task_id=task.id,
        text=ch.text,
        score=0.72,
        source_title=src.title,
        source_url=src.url,
        source_type=str(src.source_type),
        retrieved_at=src.retrieved_at,
        metadata=ch.chunk_metadata,
    )
    section = ReportGroundingService().build_grounded_section(
        query="经营风险",
        evidences=[ev],
    )
    forbidden = ["买入", "卖出", "加仓", "减仓", "目标价", "收益承诺", "个股推荐"]
    lowered = section.content.lower()
    assert all(term.lower() not in lowered for term in forbidden)


def test_grounded_section_redacts_forbidden_terms_from_evidence_text() -> None:
    now = datetime.now(timezone.utc)
    ev = RetrievedEvidence(
        chunk_id="chunk",
        source_id="source",
        task_id="task",
        text="第三方材料提到买入评级和目标价，这些词不应进入报告。",
        score=0.8,
        source_title="第三方材料",
        source_url="https://example.com",
        source_type="news",
        retrieved_at=now,
        metadata={},
    )

    section = ReportGroundingService().build_grounded_section(query="风险", evidences=[ev])

    assert "买入" not in section.content
    assert "目标价" not in section.content
    assert "【已移除】" in section.content


def test_grounded_section_max_items_zero_returns_no_citations() -> None:
    now = datetime.now(timezone.utc)
    ev = RetrievedEvidence(
        chunk_id="chunk",
        source_id="source",
        task_id="task",
        text="可展示证据",
        score=0.8,
        source_title="来源",
        source_url="https://example.com",
        source_type="news",
        retrieved_at=now,
        metadata={},
    )

    section = ReportGroundingService().build_grounded_section(
        query="风险",
        evidences=[ev],
        max_items=0,
    )

    assert "未选入" in section.content
    assert section.citations == []


def test_blank_query_raises() -> None:
    with pytest.raises(ValueError, match="query 不能为空"):
        ReportGroundingService().build_grounded_section(query="   ", evidences=[])
