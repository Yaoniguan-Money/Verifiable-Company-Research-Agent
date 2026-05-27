from __future__ import annotations

import json
from pathlib import Path

import httpx
from app.providers.search import cninfo_announcements
from app.providers.search.cninfo_announcements import CninfoAnnouncementProvider

REGRESSION_FILE = Path("data/eval/public_company_regression.json")


def _load_cases() -> list[dict]:
    payload = json.loads(REGRESSION_FILE.read_text(encoding="utf-8"))
    return payload["cases"]


def test_public_company_regression_set_is_complete() -> None:
    cases = _load_cases()

    assert len(cases) == 6
    assert len({case["company_name"] for case in cases}) == 6
    for case in cases:
        assert case["stock_code"]
        assert case["cninfo_org_id"]
        assert case["question"]
        assert case["expected_metric_groups"]
        reports = case["expected_cninfo_reports"]
        assert len(reports) >= 4
        assert all("static.cninfo.com.cn" in report["url"] for report in reports)


def test_cninfo_provider_matches_regression_reports(monkeypatch) -> None:
    cases = _load_cases()
    stock_list = [
        {
            "code": case["stock_code"],
            "orgId": case["cninfo_org_id"],
            "zwjc": case["company_name"],
        }
        for case in cases
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/new/data/szse_stock.json"):
            return httpx.Response(200, json={"stockList": stock_list}, request=request)
        if url.endswith("/new/hisAnnouncement/query"):
            body = request.content.decode("utf-8", errors="ignore")
            case = next(item for item in cases if item["stock_code"] in body)
            announcements = [
                {
                    "announcementTitle": report["title"].replace(case["company_name"], ""),
                    "adjunctUrl": report["url"].replace(cninfo_announcements.CNINFO_STATIC_BASE_URL, ""),
                    "announcementTime": 1772323200000 - idx * 31_536_000_000,
                }
                for idx, report in enumerate(case["expected_cninfo_reports"])
            ]
            return httpx.Response(200, json={"announcements": announcements}, request=request)
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=b"%PDF",
            request=request,
        )

    monkeypatch.setattr(
        cninfo_announcements,
        "_extract_pdf_text",
        lambda content: "项目 2024年 2023年\n研发费用 100亿元 90亿元\n营业收入 500亿元 450亿元",
    )
    provider = CninfoAnnouncementProvider(
        top_k=4,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    for case in cases:
        sources = provider.search(case["company_name"], case["question"])
        assert [source.title for source in sources] == [
            report["title"] for report in case["expected_cninfo_reports"]
        ]
        assert [source.url for source in sources] == [
            report["url"] for report in case["expected_cninfo_reports"]
        ]
