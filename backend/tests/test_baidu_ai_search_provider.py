from __future__ import annotations

import httpx
import pytest
from app.providers.search.baidu_ai_search import BaiduAISearchProvider
from app.schemas.common import SOURCE_LAYER_METADATA_KEY, SourceLayer


def test_baidu_ai_search_payload_uses_clean_company_research_prompt() -> None:
    provider = BaiduAISearchProvider(api_key="test-key")

    payload = provider._payload(company_name="Sample Public Co", question="经营风险")
    query = payload["messages"][0]["content"]
    instruction = str(payload["instruction"])
    combined = f"{query}\n{instruction}"

    assert "Sample Public Co" in query
    assert "年报" in query
    assert "半年报" in query
    assert "交易所公告" in query
    assert "URL" in instruction
    for broken in ("鈥", "杩", "骞", "鐧", "æ"):
        assert broken not in combined


def test_baidu_ai_search_provider_uses_reference_page_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "摘要 [ref_1]"}}],
                    "references": [
                        {
                            "title": "Demo Tech 2023 年年度报告",
                            "url": "https://example.com/report",
                            "content": "短摘要",
                            "date": "2024-03-28",
                            "type": "web",
                        }
                    ],
                },
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><p>Demo Tech 2022年研发投入为80亿元。</p><p>2023年研发投入为100亿元。</p></body></html>",
            request=request,
        )

    provider = BaiduAISearchProvider(
        api_key="test-key",
        endpoint="https://qianfan.baidubce.com/v2/ai_search/chat/completions",
        allowed_domains=["example.com"],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sources = provider.search("Demo Tech", "研发投入")

    assert len(sources) == 1
    assert sources[0].title == "Demo Tech 2023 年年度报告"
    assert sources[0].source_type == "annual_report"
    assert "2022年研发投入为80亿元" in sources[0].raw_content
    assert "2023年研发投入为100亿元" in sources[0].raw_content


def test_baidu_ai_search_provider_falls_back_to_reference_snippet() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "references": [
                        {
                            "title": "Demo Tech 公告",
                            "url": "https://example.com/announcement",
                            "content": "Demo Tech 2024年上半年营收为280亿元。",
                            "type": "web",
                        }
                    ],
                },
                request=request,
            )
        return httpx.Response(403, request=request)

    provider = BaiduAISearchProvider(
        api_key="test-key",
        allowed_domains=["example.com"],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sources = provider.search("Demo Tech", "营收")

    assert len(sources) == 1
    assert sources[0].raw_content == "Demo Tech 2024年上半年营收为280亿元。"


def test_baidu_ai_search_provider_merges_snippet_with_page_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "references": [
                        {
                            "title": "Demo Tech 2024 年年度报告摘要",
                            "url": "https://example.com/report",
                            "content": "Demo Tech 2024年营业总收入411.87亿元。",
                            "type": "web",
                        }
                    ],
                },
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body><p>投资者关系</p><p>2024年归母净利润51.53亿元。</p></body></html>",
            request=request,
        )

    provider = BaiduAISearchProvider(
        api_key="test-key",
        allowed_domains=["example.com"],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sources = provider.search("Demo Tech", "营收和利润")

    assert len(sources) == 1
    assert "营业总收入411.87亿元" in sources[0].raw_content
    assert "归母净利润51.53亿元" in sources[0].raw_content


def test_baidu_ai_search_provider_ignores_security_check_page_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "references": [
                        {
                            "title": "Demo Tech 年报简析",
                            "url": "https://example.com/report",
                            "content": "Demo Tech 2024年营业总收入411.87亿元。",
                            "type": "web",
                        }
                    ],
                },
                request=request,
            )
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body>百度安全验证 网络不给力，请稍后重试</body></html>",
            request=request,
        )

    provider = BaiduAISearchProvider(
        api_key="test-key",
        allowed_domains=["example.com"],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sources = provider.search("Demo Tech", "营收")

    assert len(sources) == 1
    assert sources[0].raw_content == "Demo Tech 2024年营业总收入411.87亿元。"


def test_baidu_ai_search_provider_filters_irrelevant_references() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "references": [
                        {
                            "title": "MBA 面试高频问题",
                            "url": "https://example.com/mba",
                            "content": "这里没有目标公司，也没有公开资料证据。",
                            "type": "web",
                        },
                        {
                            "title": "Demo Tech 2023 年年度报告",
                            "url": "https://example.com/report",
                            "content": "Demo Tech 2023年研发投入为100亿元。",
                            "type": "web",
                        },
                    ],
                },
                request=request,
            )
        return httpx.Response(403, request=request)

    provider = BaiduAISearchProvider(
        api_key="test-key",
        fetch_reference_pages=False,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sources = provider.search("Demo Tech", "研发投入")

    assert len(sources) == 1
    assert sources[0].title == "Demo Tech 2023 年年度报告"


def test_baidu_ai_search_provider_requires_usable_references() -> None:
    provider = BaiduAISearchProvider(
        api_key="test-key",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"references": []}, request=request)
            )
        ),
    )

    with pytest.raises(ValueError, match="no usable references"):
        provider.search("demo tech", "经营风险")


def test_baidu_ai_search_provider_api_error_should_fail_instead_of_fallback_mock() -> None:
    provider = BaiduAISearchProvider(
        api_key="test-key",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(401, json={"error": "unauthorized"}, request=request)
            )
        ),
    )

    with pytest.raises(httpx.HTTPStatusError):
        provider.search("Sample Public Co", "经营风险")


def test_baidu_ai_search_provider_does_not_add_builtin_company_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "references": [
                        {
                            "title": "Sample Public Co 雪球讨论",
                            "url": "https://xueqiu.com/123456",
                            "content": "Sample Public Co 营收 与 净利润 讨论。",
                            "type": "web",
                        },
                        {
                            "title": "Sample Public Co 百家号观察",
                            "url": "https://baijiahao.baidu.com/s?id=123",
                            "content": "Sample Public Co 公告 与 经营风险。",
                            "type": "web",
                        },
                    ],
                },
                request=request,
            )
        return httpx.Response(403, request=request)

    provider = BaiduAISearchProvider(
        api_key="test-key",
        fetch_reference_pages=False,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sources = provider.search("Sample Public Co", "优先使用公司官网、交易所公告、年报、半年报")

    assert len(sources) == 2
    assert {source.url for source in sources} == {
        "https://xueqiu.com/123456",
        "https://baijiahao.baidu.com/s?id=123",
    }
    assert all((source.credibility_score or 1) < 0.6 for source in sources)


def test_baidu_ai_search_provider_prioritizes_upstream_official_pdf_over_low_authority() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "references": [
                        {
                            "title": "Sample Public Co 雪球讨论",
                            "url": "https://xueqiu.com/123456",
                            "content": "Sample Public Co 营收 与 净利润 讨论。",
                            "type": "web",
                        },
                        {
                            "title": "Sample Public Co 2024 年年度报告",
                            "url": "https://www.hkexnews.hk/listedco/listconews/sehk/2024/annual_report.pdf",
                            "content": "Sample Public Co 年报 研发投入 与 经营风险。",
                            "type": "web",
                        },
                    ],
                },
                request=request,
            )
        return httpx.Response(403, request=request)

    provider = BaiduAISearchProvider(
        api_key="test-key",
        fetch_reference_pages=False,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    sources = provider.search("Sample Public Co", "优先使用年报 PDF")

    assert sources[0].source_metadata is not None
    assert sources[0].source_metadata[SOURCE_LAYER_METADATA_KEY] == SourceLayer.OFFICIAL_PDF.value
    assert any((source.credibility_score or 1) < 0.6 for source in sources)
