from __future__ import annotations

from datetime import datetime, timezone

import httpx
from app.providers.search.baidu_reference import BaiduReferenceProcessor
from app.schemas.common import (
    SOURCE_LAYER_METADATA_KEY,
    SourceLayer,
)


def _processor() -> BaiduReferenceProcessor:
    return BaiduReferenceProcessor(
        company_name="Sample Public Co",
        allowed_domains=[],
        fetch_reference_pages=False,
    )


def test_baidu_reference_processor_marks_official_domains_high_authority() -> None:
    processor = _processor()
    now = datetime.now(timezone.utc)

    sources = processor.sources_from_references(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))),
        references=[
            {
                "title": "Sample Public Co 2024 年年度报告",
                "url": "https://www.hkexnews.hk/listedco/listconews/sehk/2024/annual_report.pdf",
                "content": "Sample Public Co 年报 研发投入 与 经营风险。",
                "type": "web",
            },
            {
                "title": "Sample Public Co 投资者关系",
                "url": "https://www.hkexnews.hk/",
                "content": "Sample Public Co 公告 与 研发信息。",
                "type": "web",
            },
        ],
        now=now,
    )

    assert len(sources) == 2
    assert all((item.credibility_score or 0) >= 0.85 for item in sources)
    assert sources[0].source_metadata is not None
    assert sources[0].source_metadata[SOURCE_LAYER_METADATA_KEY] == SourceLayer.OFFICIAL_PDF.value


def test_baidu_reference_processor_marks_low_authority_domains_low_priority() -> None:
    processor = _processor()
    now = datetime.now(timezone.utc)

    sources = processor.sources_from_references(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))),
        references=[
            {
                "title": "Sample Public Co 经营讨论",
                "url": "https://xueqiu.com/123456",
                "content": "Sample Public Co 营收 与 净利润 讨论。",
                "type": "web",
            },
            {
                "title": "Sample Public Co 百家号观察",
                "url": "https://baijiahao.baidu.com/s?id=123",
                "content": "Sample Public Co 公告 与 风险。",
                "type": "web",
            },
        ],
        now=now,
    )

    assert len(sources) == 2
    assert all((item.credibility_score or 1) < 0.6 for item in sources)
    assert processor.source_quality_insufficient(sources)


def test_baidu_reference_processor_filters_training_exam_pages() -> None:
    processor = _processor()
    now = datetime.now(timezone.utc)

    sources = processor.sources_from_references(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, request=request))),
        references=[
            {
                "title": "Sample Public Co 2024 年年度报告",
                "url": "https://www.szse.cn/disclosure/listed/notice.html",
                "content": "Sample Public Co 年报 研发投入 与 营收。",
                "type": "web",
            },
            {
                "title": "Sample Public Co 财务分析考试题",
                "url": "https://www.zhihu.com/question/12345",
                "content": "这里是考试题，不是公开披露正文。",
                "type": "web",
            },
        ],
        now=now,
    )

    assert len(sources) == 1
    assert "年度报告" in sources[0].title


def test_baidu_reference_processor_does_not_add_company_specific_fallback_sources() -> None:
    processor = _processor()
    original_sources = processor.sources_from_references(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, request=request))),
        references=[
            {
                "title": "Sample Public Co 百家号观察",
                "url": "https://baijiahao.baidu.com/s?id=123",
                "content": "Sample Public Co 公告 与 风险。",
                "type": "web",
            }
        ],
        now=datetime.now(timezone.utc),
    )

    merged, disclosure_count, fallback_count = processor.augment_with_official_sources_if_needed(
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403, request=request))),
        sources=original_sources,
        now=datetime.now(timezone.utc),
    )

    assert merged == original_sources
    assert disclosure_count == 0
    assert fallback_count == 0
