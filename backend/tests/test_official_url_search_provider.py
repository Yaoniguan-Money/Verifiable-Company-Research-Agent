from __future__ import annotations

import httpx
import pytest
from app.providers.search import official_urls
from app.providers.search.official_urls import OfficialUrlSearchProvider


def test_official_url_provider_fetches_whitelisted_html(tmp_path) -> None:
    company_dir = tmp_path / "demo_tech"
    company_dir.mkdir()
    (company_dir / "official_urls.json").write_text(
        """[
  {
    "title": "Demo Tech 官网经营信息",
    "url": "https://example.com/investor/demo-tech",
    "source_type": "official_website",
    "published_at": "2024-09-01",
    "credibility_score": 0.9
  }
]""",
        encoding="utf-8",
    )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="""
            <html><head><style>.x{}</style><script>ignored()</script></head>
            <body><h1>Demo Tech</h1><p>2023年研发投入为100亿元。</p><p>2023年营收为500亿元。</p></body></html>
            """,
            request=request,
        )
    )
    client = httpx.Client(transport=transport)

    sources = OfficialUrlSearchProvider(
        root_dir=str(tmp_path),
        allowed_domains=["example.com"],
        client=client,
    ).search("demo tech", "研发投入")

    assert len(sources) == 1
    assert sources[0].title == "Demo Tech 官网经营信息"
    assert sources[0].source_type == "official_website"
    assert sources[0].credibility_score == 0.9
    assert "2023年研发投入为100亿元" in sources[0].raw_content
    assert "ignored" not in sources[0].raw_content


def test_official_url_provider_strips_manifest_fields(tmp_path) -> None:
    company_dir = tmp_path / "demo_tech"
    company_dir.mkdir()
    (company_dir / "official_urls.json").write_text(
        """[{
  "title": " Demo Tech 官网 ",
  "url": " https://example.com/investor/demo-tech ",
  "source_type": " official_website "
}]""",
        encoding="utf-8",
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="2023年研发投入为100亿元。",
                request=request,
            )
        )
    )

    sources = OfficialUrlSearchProvider(
        root_dir=str(tmp_path),
        allowed_domains=["example.com"],
        client=client,
    ).search("demo tech", "研发投入")

    assert sources[0].title == "Demo Tech 官网"
    assert sources[0].url == "https://example.com/investor/demo-tech"
    assert sources[0].source_type == "official_website"


def test_official_url_provider_ignores_non_finite_score(tmp_path) -> None:
    company_dir = tmp_path / "demo_tech"
    company_dir.mkdir()
    (company_dir / "official_urls.json").write_text(
        """[{"url": "https://example.com/report", "credibility_score": "NaN"}]""",
        encoding="utf-8",
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                text="2023年研发投入为100亿元。",
                request=request,
            )
        )
    )

    sources = OfficialUrlSearchProvider(
        root_dir=str(tmp_path),
        allowed_domains=["example.com"],
        client=client,
    ).search("demo tech", "研发投入")

    assert sources[0].credibility_score == 0.82


def test_official_url_provider_blocks_non_whitelisted_domain(tmp_path) -> None:
    company_dir = tmp_path / "demo_tech"
    company_dir.mkdir()
    (company_dir / "official_urls.json").write_text(
        """[{"url": "https://untrusted.example.net/report"}]""",
        encoding="utf-8",
    )

    provider = OfficialUrlSearchProvider(
        root_dir=str(tmp_path),
        allowed_domains=["example.com"],
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
    )

    with pytest.raises(ValueError, match="not in OFFICIAL_URL_ALLOWED_DOMAINS"):
        provider.search("demo tech", "经营风险")


def test_official_url_provider_extracts_pdf_text(tmp_path, monkeypatch) -> None:
    company_dir = tmp_path / "demo_tech"
    company_dir.mkdir()
    (company_dir / "official_urls.json").write_text(
        """[{
  "title": "Demo Tech 2024 年年度报告",
  "url": "https://example.com/report.pdf",
  "source_type": "annual_report",
  "credibility_score": 0.95
}]""",
        encoding="utf-8",
    )

    class FakePage:
        def extract_text(self) -> str:
            return "Demo Tech 2024年研发投入为120亿元。"

    class FakeReader:
        def __init__(self, stream) -> None:  # noqa: ANN001
            self.pages = [FakePage()]

    monkeypatch.setattr(official_urls, "PdfReader", FakeReader)

    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/pdf"},
                content=b"%PDF-1.4 fake",
                request=request,
            )
        )
    )

    sources = OfficialUrlSearchProvider(
        root_dir=str(tmp_path),
        allowed_domains=["example.com"],
        client=client,
    ).search("demo tech", "研发投入")

    assert len(sources) == 1
    assert sources[0].source_type == "annual_report"
    assert "2024年研发投入为120亿元" in sources[0].raw_content
