from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from app.providers.search.official_urls import (
    _extract_pdf_text,
    _normalize_text,
    _ReadableHTMLParser,
)
from app.schemas.common import (
    CONTENT_FETCH_STATUS_METADATA_KEY,
    SOURCE_LAYER_METADATA_KEY,
    ContentFetchStatus,
    SourceLayer,
    SourceType,
    authority_label,
    source_quality_insufficient,
)
from app.schemas.source import SourceCreate

AUTHORITATIVE_DOMAINS = frozenset(
    {
        "hkexnews.hk",
        "hkex.com.hk",
        "sse.com.cn",
        "szse.cn",
        "cninfo.com.cn",
        "gov.cn",
    }
)

LOW_AUTHORITY_DOMAINS = frozenset(
    {
        "baijiahao.baidu.com",
        "zhihu.com",
        "xueqiu.com",
        "mp.weixin.qq.com",
        "wjx.cn",
        "11467.com",
    }
)

BUSINESS_REGISTRY_DOMAINS = frozenset(
    {
        "aiqicha.baidu.com",
        "qcc.com",
        "tianyancha.com",
        "gsxt.gov.cn",
    }
)

BLOCKED_PAGE_KEYWORDS = (
    "考试题",
    "试卷",
    "题库",
    "培训",
    "课程",
    "论文下载",
    "问卷",
    "问答社区",
    "面试题",
    "interview",
)

EVIDENCE_KEYWORDS = (
    "年报",
    "年度报告",
    "半年报",
    "季报",
    "研发",
    "研发费用",
    "研发投入",
    "营收",
    "营业收入",
    "净利润",
    "经营风险",
    "风险因素",
    "财务",
    "业绩",
    "公告",
    "投资者关系",
    "监管",
    "交易所",
    "企业信息",
    "企业信用",
    "工商",
    "经营范围",
    "法定代表人",
    "注册资本",
    "成立日期",
    "统一社会信用代码",
    "公司简介",
    "公司介绍",
    "主营",
    "主要业务",
    "业务板块",
    "产品",
    "服务",
)


class BaiduReferenceProcessor:
    """把百度 AI 搜索引用转换成项目内部 Source。

    百度返回的是候选引用，不等于已验证来源；这里负责去重、抓取正文、过滤无关结果，
    让 provider 主类只保留 API 调用职责。
    """

    def __init__(
        self,
        *,
        company_name: str,
        allowed_domains: list[str],
        fetch_reference_pages: bool,
    ) -> None:
        self.company_name = company_name
        self.allowed_domains = allowed_domains
        self.fetch_reference_pages = fetch_reference_pages

    def authority_label(self, source: SourceCreate) -> str:
        return authority_label(source.credibility_score).value

    def source_quality_insufficient(self, sources: list[SourceCreate]) -> bool:
        return source_quality_insufficient(sources)

    def augment_with_official_sources_if_needed(
        self,
        *,
        client: httpx.Client,
        sources: list[SourceCreate],
        now: datetime,
    ) -> tuple[list[SourceCreate], int, int]:
        return sources, 0, 0

    def sources_from_references(
        self,
        *,
        client: httpx.Client,
        references: list[object],
        now: datetime,
    ) -> list[SourceCreate]:
        out: list[SourceCreate] = []
        seen_urls: set[str] = set()
        for item in references:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            title = str(item.get("title") or item.get("web_anchor") or "百度 AI 搜索引用")
            if not url or url in seen_urls or not self._domain_allowed(url):
                continue
            credibility_score = self._credibility_for(title=title, url=url)
            if credibility_score <= 0:
                continue
            seen_urls.add(url)

            snippet = str(item.get("content") or "")
            body = self._fetch_reference_body(client=client, url=url) if self.fetch_reference_pages else ""
            raw_content = merge_reference_text(snippet=snippet, body=body)
            if not raw_content or not self._looks_relevant(title=title, url=url, raw_content=raw_content):
                continue

            out.append(
                SourceCreate(
                    task_id="TBD_BY_WORKFLOW",
                    title=title,
                    url=url,
                    source_type=self._infer_source_type(title=title, url=url, raw_type=item.get("type")),
                    published_at=self._parse_datetime(item.get("date")),
                    retrieved_at=now,
                    raw_content=raw_content,
                    credibility_score=credibility_score,
                    source_metadata={
                        SOURCE_LAYER_METADATA_KEY: self._source_layer_for(title=title, url=url).value,
                        CONTENT_FETCH_STATUS_METADATA_KEY: (
                            ContentFetchStatus.FETCHED_CONTENT.value if body else ContentFetchStatus.SNIPPET_ONLY.value
                        ),
                    },
                )
            )
        return sorted(out, key=lambda item: item.credibility_score or 0, reverse=True)

    def _looks_relevant(self, *, title: str, url: str, raw_content: str) -> bool:
        text = _normalize_match_text(f"{title}\n{url}\n{raw_content[:2000]}")
        if any(keyword in text for keyword in BLOCKED_PAGE_KEYWORDS):
            return False
        company = _normalize_match_text(self.company_name)
        compact_company = _compact_identity(self.company_name)
        compact_text = _compact_identity(text)
        has_company = bool(company and (company in text or compact_company in compact_text))
        if has_company and any(keyword in text for keyword in EVIDENCE_KEYWORDS):
            return True
        # Official disclosure pages are often sparse landing pages whose title or
        # snippet carries the evidence signal while the fetched body is generic.
        return has_company and self._is_authoritative_url(url)

    def _fetch_reference_body(self, *, client: httpx.Client, url: str) -> str:
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return ""
        content_type = response.headers.get("content-type", "").lower()
        url_path = urlparse(str(response.url)).path.lower()
        if "pdf" in content_type or url_path.endswith(".pdf"):
            return _extract_pdf_text(response.content)
        if "html" in content_type:
            parser = _ReadableHTMLParser()
            parser.feed(response.text)
            body = _normalize_text(parser.text())
            if "百度安全验证" in body or "网络不给力" in body:
                return ""
            return body
        if "text" in content_type or "json" in content_type:
            body = _normalize_text(response.text)
            if "百度安全验证" in body or "网络不给力" in body:
                return ""
            return body
        return ""

    def _domain_allowed(self, url: str) -> bool:
        if not self.allowed_domains:
            return True
        host = (urlparse(url).hostname or "").lower()
        return any(host == domain or host.endswith(f".{domain}") for domain in self.allowed_domains)

    def _infer_source_type(self, *, title: str, url: str, raw_type: object) -> SourceType:
        host = (urlparse(url).hostname or "").lower()
        text = f"{title} {url} {raw_type or ''}".lower()
        if "annual" in text or "年报" in text or "年度报告" in text:
            return SourceType.ANNUAL_REPORT
        if "公告" in text or "announcement" in text or "disclosure" in text:
            return SourceType.ANNOUNCEMENT
        if "gov" in text or "政府" in text or "监管" in text:
            return SourceType.GOVERNMENT
        if any(mark in text for mark in ("招聘", "hiring", "job", "career")):
            return SourceType.HIRING
        if self._host_matches(host, BUSINESS_REGISTRY_DOMAINS):
            return SourceType.OTHER
        if "news" in text or "新闻" in text or raw_type == "web":
            return SourceType.NEWS
        return SourceType.OTHER

    def _parse_datetime(self, raw: object) -> datetime | None:
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(str(raw))
        except ValueError:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _credibility_for(self, *, title: str, url: str) -> float:
        host = (urlparse(url).hostname or "").lower()
        text = f"{title} {host}".lower()
        if any(host == domain or host.endswith(f".{domain}") for domain in AUTHORITATIVE_DOMAINS):
            return 0.96
        if self._host_matches(host, LOW_AUTHORITY_DOMAINS):
            return 0.46
        if self._host_matches(host, BUSINESS_REGISTRY_DOMAINS):
            return 0.72
        if any(mark in text for mark in ("官网", "official", "investor", "ir.", "investor-relations")):
            return 0.84
        if any(mark in text for mark in ("年报", "年度报告", "交易所", "监管披露", "公告")):
            return 0.78
        return 0.68

    def _source_layer_for(self, *, title: str, url: str) -> SourceLayer:
        host = (urlparse(url).hostname or "").lower()
        text = f"{title} {url}".lower()
        if "pdf" in text and any(
            host == domain or host.endswith(f".{domain}") for domain in AUTHORITATIVE_DOMAINS
        ):
            return SourceLayer.OFFICIAL_PDF
        if any(host == domain or host.endswith(f".{domain}") for domain in AUTHORITATIVE_DOMAINS):
            return SourceLayer.OFFICIAL_DISCLOSURE_PAGE
        if self._host_matches(host, LOW_AUTHORITY_DOMAINS):
            return SourceLayer.THIRD_PARTY_BACKGROUND
        return SourceLayer.THIRD_PARTY_BACKGROUND

    def _is_authoritative_url(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return self._host_matches(host, AUTHORITATIVE_DOMAINS)

    def _host_matches(self, host: str, domains: frozenset[str]) -> bool:
        return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def merge_reference_text(*, snippet: str, body: str) -> str:
    normalized_snippet = _normalize_text(snippet)
    normalized_body = _normalize_text(body)
    if normalized_snippet and normalized_body and normalized_snippet not in normalized_body:
        return f"{normalized_snippet}\n\n{normalized_body}"
    return normalized_body or normalized_snippet


def _normalize_match_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).lower()


def _compact_identity(value: str) -> str:
    normalized = _normalize_match_text(value)
    return re.sub(r"[\W_]+", "", normalized)
