from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from app.providers.search.base import SearchProvider
from app.providers.search.official_urls import _extract_pdf_text, _normalize_text
from app.schemas.common import (
    CONTENT_FETCH_STATUS_METADATA_KEY,
    SOURCE_LAYER_METADATA_KEY,
    ContentFetchStatus,
    SourceLayer,
    SourceType,
)
from app.schemas.source import SourceCreate
from app.services.question_time_scope import ResearchTimeScope, parse_research_time_scope

CNINFO_STATIC_BASE_URL = "https://static.cninfo.com.cn/"
CNINFO_STOCK_LIST_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
CNINFO_ANNOUNCEMENT_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"


@dataclass(frozen=True, slots=True)
class CninfoSecurity:
    code: str
    org_id: str
    name: str
    column: str
    plate: str


@dataclass(frozen=True, slots=True)
class CninfoAnnouncement:
    title: str
    url: str
    published_at: datetime | None
    source_type: SourceType


class CninfoAnnouncementProvider(SearchProvider):
    """从巨潮资讯拉取上市公司年报/半年报 PDF。

    这是 A 股公开资料的高可信入口：只取法定披露平台的公告 PDF，不把搜索摘要当作事实。
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
        top_k: int = 6,
        lookback_years: int = 4,
        max_source_chars: int = 300_000,
        client: httpx.Client | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.top_k = top_k
        self.lookback_years = lookback_years
        self.max_source_chars = max_source_chars
        self._client = client

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        client = self._client or httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers=self._headers(),
        )
        should_close = self._client is None
        time_scope = parse_research_time_scope(
            question,
            default_lookback_years=self.lookback_years,
        )
        try:
            security = self._resolve_security(client=client, company_name=company_name)
            announcements = self._query_announcements(
                client=client,
                security=security,
                time_scope=time_scope,
            )
            sources = self._download_sources(
                client=client,
                security=security,
                announcements=announcements,
                question=question,
            )
        finally:
            if should_close:
                client.close()

        if not sources:
            raise ValueError(f"Cninfo import produced no readable annual/semiannual reports for {company_name!r}")
        return sources

    def _resolve_security(self, *, client: httpx.Client, company_name: str) -> CninfoSecurity:
        response = client.get(CNINFO_STOCK_LIST_URL)
        response.raise_for_status()
        stock_list = response.json().get("stockList") or []
        normalized_query = company_name.strip().lower()
        for item in stock_list:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "")
            name = str(item.get("zwjc") or "")
            if normalized_query in {code.lower(), name.lower()} or normalized_query in name.lower():
                org_id = str(item.get("orgId") or "")
                if code and name and org_id:
                    column, plate = _market_params_for_code(code)
                    return CninfoSecurity(
                        code=code,
                        org_id=org_id,
                        name=name,
                        column=column,
                        plate=plate,
                    )
        raise ValueError(f"Cannot resolve {company_name!r} in CNINFO stock list")

    def _query_announcements(
        self,
        *,
        client: httpx.Client,
        security: CninfoSecurity,
        time_scope: ResearchTimeScope | None = None,
    ) -> list[CninfoAnnouncement]:
        effective_top_k = (
            time_scope.suggested_source_limit(default_top_k=self.top_k)
            if time_scope is not None
            else self.top_k
        )
        response = client.post(
            CNINFO_ANNOUNCEMENT_QUERY_URL,
            data={
                "pageNum": "1",
                "pageSize": str(max(effective_top_k * 4, 20)),
                "tabName": "fulltext",
                "column": security.column,
                "stock": f"{security.code},{security.org_id}",
                "searchkey": "",
                "secid": "",
                "plate": security.plate,
                "category": "category_ndbg_szsh;category_bndbg_szsh;",
                "trade": "",
                "seDate": self._date_range(time_scope),
            },
        )
        response.raise_for_status()
        raw_items = response.json().get("announcements") or []
        candidates: list[CninfoAnnouncement] = []
        seen_urls: set[str] = set()
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            title = _normalize_text(str(item.get("announcementTitle") or ""))
            adjunct_url = str(item.get("adjunctUrl") or "")
            if not title or not adjunct_url or not self._is_primary_report(title):
                continue
            url = CNINFO_STATIC_BASE_URL + adjunct_url.lstrip("/")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            candidates.append(
                CninfoAnnouncement(
                    title=_announcement_display_title(security.name, title),
                    url=url,
                    published_at=self._parse_cninfo_time(item.get("announcementTime")),
                    source_type=SourceType.ANNUAL_REPORT if "年度报告" in title else SourceType.ANNOUNCEMENT,
                )
            )
        if time_scope is not None and time_scope.strict:
            allowed = time_scope.preferred_years()
            candidates = [
                item
                for item in candidates
                if (year := self._report_year(item.title, item.published_at)) is None
                or year in allowed
            ]
        elif time_scope is not None:
            preferred = time_scope.preferred_years()

            def _announcement_rank(item: CninfoAnnouncement) -> tuple[int, tuple[int, float]]:
                year = self._report_year(item.title, item.published_at) or 0
                in_pref = 0 if year in preferred else 1
                return (in_pref, self._report_priority(item))

            return sorted(candidates, key=_announcement_rank)[:effective_top_k]
        return sorted(candidates, key=self._report_priority)[:effective_top_k]

    def _download_sources(
        self,
        *,
        client: httpx.Client,
        security: CninfoSecurity,
        announcements: list[CninfoAnnouncement],
        question: str,
    ) -> list[SourceCreate]:
        now = datetime.now(timezone.utc)
        sources: list[SourceCreate] = []
        for item in announcements:
            try:
                response = client.get(item.url)
                response.raise_for_status()
            except httpx.HTTPError:
                continue
            content_type = response.headers.get("content-type", "").lower()
            is_pdf = "pdf" in content_type or item.url.lower().endswith(".pdf")
            raw_text = _extract_pdf_text(response.content) if is_pdf else response.text
            content = _focus_report_content(
                text=raw_text,
                company_name=security.name,
                question=question,
                max_chars=self.max_source_chars,
            )
            if not content:
                continue
            metadata: dict = {
                SOURCE_LAYER_METADATA_KEY: SourceLayer.OFFICIAL_PDF.value
                if is_pdf
                else SourceLayer.OFFICIAL_DISCLOSURE_PAGE.value,
                CONTENT_FETCH_STATUS_METADATA_KEY: ContentFetchStatus.FETCHED_CONTENT.value,
            }
            if is_pdf:
                metadata["pdf_url"] = item.url
            sources.append(
                SourceCreate(
                    task_id="TBD_BY_WORKFLOW",
                    title=item.title,
                    url=item.url,
                    source_type=item.source_type,
                    published_at=item.published_at,
                    retrieved_at=now,
                    raw_content=content,
                    credibility_score=0.95,
                    source_metadata=metadata,
                )
            )
        return sources

    def _is_primary_report(self, title: str) -> bool:
        if "摘要" in title or "英文" in title or "取消" in title or "更正" in title:
            return False
        return "年度报告" in title or "半年度报告" in title

    def _report_priority(self, item: CninfoAnnouncement) -> tuple[int, float]:
        is_semiannual = "半年度报告" in item.title
        timestamp = item.published_at.timestamp() if item.published_at else 0.0
        return (1 if is_semiannual else 0, -timestamp)

    def _date_range(self, time_scope: ResearchTimeScope | None = None) -> str:
        now = datetime.now(timezone.utc)
        if time_scope is not None:
            span = min(time_scope.lookback_years, self.lookback_years)
        else:
            span = self.lookback_years
        return f"{now.year - span}-01-01~{now.year}-12-31"

    def _report_year(self, title: str, published_at: datetime | None) -> int | None:
        match = re.search(r"(20\d{2})", title)
        if match:
            return int(match.group(1))
        if published_at:
            return published_at.year
        return None

    def _parse_cninfo_time(self, raw: object) -> datetime | None:
        if raw is None:
            return None
        try:
            timestamp = int(raw) / 1000
        except (TypeError, ValueError):
            return None
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
            "Accept": "application/json,text/javascript,*/*;q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }


def _focus_report_content(
    *,
    text: str,
    company_name: str,
    question: str,
    max_chars: int,
) -> str:
    normalized = _normalize_text(text)
    if len(normalized) <= max_chars:
        return normalized

    priority_keywords = (
        "研发费用",
        "研发投入",
        "产能状况",
        "快报产量",
        "快报销量",
        "销售收入",
        "营业收入和营业成本",
        "主营业务收入",
        "收入分解",
    )
    keywords = (
        *priority_keywords,
        company_name,
        "研发",
        "研发投入",
        "研发费用",
        "营业收入",
        "营收",
        "收入结构",
        "净利润",
        "产能",
        "产量",
        "销量",
        "风险",
        "经营风险",
        *[part for part in question.replace("，", " ").replace("、", " ").split() if len(part) >= 2],
    )
    windows: list[str] = [normalized[:3000]]
    seen_ranges: set[tuple[int, int]] = set()
    for keyword in keywords:
        start = normalized.find(keyword)
        while start != -1 and sum(len(item) for item in windows) < max_chars:
            left = max(0, start - 2600)
            right = min(len(normalized), start + 5200)
            window_key = (left, right)
            if window_key not in seen_ranges:
                windows.append(normalized[left:right])
                seen_ranges.add(window_key)
            start = normalized.find(keyword, start + len(keyword))
    return _normalize_text("\n\n".join(windows))[:max_chars]


def _market_params_for_code(code: str) -> tuple[str, str]:
    normalized = code.strip()
    if normalized.startswith(("6", "9")):
        return "sse", "sh"
    if normalized.startswith(("4", "8")):
        return "bj", "bj"
    return "szse", "sz"


def _announcement_display_title(company_name: str, title: str) -> str:
    normalized_company = company_name.strip()
    normalized_title = title.strip()
    if normalized_company and normalized_title.startswith(normalized_company):
        return normalized_title
    return f"{normalized_company}{normalized_title}"
