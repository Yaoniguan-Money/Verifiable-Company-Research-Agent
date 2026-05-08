from __future__ import annotations

import httpx
import pytest
from app.providers.search import cninfo_announcements
from app.providers.search.cninfo_announcements import CninfoAnnouncementProvider


def test_cninfo_provider_downloads_primary_reports(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/new/data/szse_stock.json"):
            return httpx.Response(
                200,
                json={
                    "stockList": [
                        {"code": "002594", "orgId": "gshk0001211", "zwjc": "样例股份"},
                    ]
                },
                request=request,
            )
        if str(request.url).endswith("/new/hisAnnouncement/query"):
            return httpx.Response(
                200,
                json={
                    "announcements": [
                        {
                            "announcementTitle": "2024年年度报告摘要",
                            "adjunctUrl": "finalpage/2025-03-25/summary.PDF",
                            "announcementTime": 1742832000000,
                        },
                        {
                            "announcementTitle": "2024年年度报告",
                            "adjunctUrl": "finalpage/2025-03-25/full.PDF",
                            "announcementTime": 1742832000000,
                        },
                        {
                            "announcementTitle": "2024年半年度报告",
                            "adjunctUrl": "finalpage/2024-08-29/half.PDF",
                            "announcementTime": 1724860800000,
                        },
                        {
                            "announcementTitle": "2023年年度报告",
                            "adjunctUrl": "finalpage/2024-03-28/full-2023.PDF",
                            "announcementTime": 1711584000000,
                        },
                    ]
                },
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF",
            request=request,
        )

    monkeypatch.setattr(
        cninfo_announcements,
        "_extract_pdf_text",
        lambda content: "样例股份 2024年研发投入为542亿元。经营风险包括海外市场竞争和产能爬坡。",
    )
    provider = CninfoAnnouncementProvider(
        top_k=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sources = provider.search("样例股份", "近三年研发投入变化和经营风险")

    assert len(sources) == 2
    assert sources[0].title == "样例股份2024年年度报告"
    assert sources[0].url == "https://static.cninfo.com.cn/finalpage/2025-03-25/full.PDF"
    assert sources[1].title == "样例股份2023年年度报告"
    assert sources[0].source_type == "annual_report"
    assert sources[0].credibility_score == 0.95
    assert "研发投入为542亿元" in sources[0].raw_content
    assert "摘要" not in sources[0].title


def test_cninfo_provider_raises_when_company_cannot_be_resolved() -> None:
    provider = CninfoAnnouncementProvider(
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"stockList": []}, request=request)
            )
        )
    )

    with pytest.raises(ValueError, match="Cannot resolve"):
        provider.search("不存在公司", "研发")
