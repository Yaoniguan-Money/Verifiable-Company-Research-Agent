from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

import httpx
from app.providers.search.base import SearchProvider
from app.schemas.common import (
    CONTENT_FETCH_STATUS_METADATA_KEY,
    SOURCE_LAYER_METADATA_KEY,
    ContentFetchStatus,
    SourceLayer,
    SourceType,
)
from app.schemas.source import SourceCreate
from pypdf import PdfReader


@dataclass(frozen=True, slots=True)
class OfficialUrlEntry:
    url: str
    title: str | None = None
    source_type: SourceType = SourceType.OTHER
    published_at: datetime | None = None
    credibility_score: float = 0.82


class OfficialUrlSearchProvider(SearchProvider):
    """按白名单抓取用户维护的官方 URL 清单。

    这是联网搜索前的稳妥过渡层：系统只抓明确给出的 URL，不自动扩散爬取。
    """

    MANIFEST_NAMES = ("official_urls.json", "urls.json")

    def __init__(
        self,
        *,
        root_dir: str = "./data/imports",
        allowed_domains: list[str] | None = None,
        timeout_seconds: float = 15.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.allowed_domains = [domain.lower().strip() for domain in allowed_domains or [] if domain.strip()]
        self.timeout_seconds = timeout_seconds
        self._client = client

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        entries = self._load_entries(company_name)
        if not entries:
            raise ValueError(f"No official URL manifest found for {company_name!r} under {self.root_dir}")

        now = datetime.now(timezone.utc)
        out: list[SourceCreate] = []
        client = self._client or httpx.Client(timeout=self.timeout_seconds, follow_redirects=True)
        should_close = self._client is None
        try:
            for entry in entries:
                self._ensure_allowed(entry.url)
                response = client.get(entry.url)
                response.raise_for_status()
                body = self._extract_text(response)
                if not body:
                    continue
                out.append(
                    SourceCreate(
                        task_id="TBD_BY_WORKFLOW",
                        title=entry.title or self._title_from_url(entry.url),
                        url=entry.url,
                        source_type=entry.source_type,
                        published_at=entry.published_at,
                        retrieved_at=now,
                        raw_content=body,
                        credibility_score=entry.credibility_score,
                        source_metadata={
                            SOURCE_LAYER_METADATA_KEY: self._source_layer(response).value,
                            CONTENT_FETCH_STATUS_METADATA_KEY: ContentFetchStatus.FETCHED_CONTENT.value,
                        },
                    )
                )
        finally:
            if should_close:
                client.close()

        if not out:
            raise ValueError(f"Official URL import produced no readable content for {company_name!r}")
        return out

    def _load_entries(self, company_name: str) -> list[OfficialUrlEntry]:
        manifest = self._manifest_path(company_name)
        if manifest is None:
            return []
        data = json.loads(manifest.read_text(encoding="utf-8"))
        items = data.get("sources", data) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError(f"Official URL manifest must be a list or {{'sources': [...]}}: {manifest}")
        return [self._parse_entry(item, manifest) for item in items]

    def _manifest_path(self, company_name: str) -> Path | None:
        for directory in (self.root_dir / company_name, self.root_dir / self._slug(company_name)):
            for name in self.MANIFEST_NAMES:
                candidate = directory / name
                if candidate.exists():
                    return candidate
        return None

    def _parse_entry(self, item: object, manifest: Path) -> OfficialUrlEntry:
        if not isinstance(item, dict) or not item.get("url"):
            raise ValueError(f"Invalid official URL entry in {manifest}")
        return OfficialUrlEntry(
            url=str(item["url"]).strip(),
            title=str(item["title"]).strip() if item.get("title") else None,
            source_type=self._source_type(item.get("source_type")),
            published_at=self._parse_datetime(item.get("published_at")),
            credibility_score=self._parse_score(item.get("credibility_score")),
        )

    def _ensure_allowed(self, url: str) -> None:
        host = (urlparse(url).hostname or "").lower()
        if not host:
            raise ValueError(f"Invalid URL: {url}")
        if self.allowed_domains and not any(host == domain or host.endswith(f".{domain}") for domain in self.allowed_domains):
            raise ValueError(f"URL host {host!r} is not in OFFICIAL_URL_ALLOWED_DOMAINS")

    def _extract_text(self, response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "").lower()
        url_path = urlparse(str(response.url)).path.lower()
        if "pdf" in content_type or url_path.endswith(".pdf"):
            return _extract_pdf_text(response.content)
        if "html" in content_type:
            parser = _ReadableHTMLParser()
            parser.feed(response.text)
            return _normalize_text(parser.text())
        return _normalize_text(response.text)

    def _source_layer(self, response: httpx.Response) -> SourceLayer:
        content_type = response.headers.get("content-type", "").lower()
        url_path = urlparse(str(response.url)).path.lower()
        if "pdf" in content_type or url_path.endswith(".pdf"):
            return SourceLayer.OFFICIAL_PDF
        return SourceLayer.OFFICIAL_DISCLOSURE_PAGE

    def _source_type(self, raw: object) -> SourceType:
        if not raw:
            return SourceType.OTHER
        try:
            return SourceType(str(raw).strip())
        except ValueError:
            return SourceType.OTHER

    def _parse_datetime(self, raw: object) -> datetime | None:
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(str(raw))
        except ValueError:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _parse_score(self, raw: object) -> float:
        if raw is None:
            return 0.82
        try:
            score = float(raw)
        except (TypeError, ValueError):
            return 0.82
        if not isfinite(score):
            return 0.82
        return max(0.0, min(1.0, score))

    def _title_from_url(self, url: str) -> str:
        path = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
        return path.replace("-", " ").replace("_", " ") or urlparse(url).hostname or "official source"

    def _slug(self, value: str) -> str:
        return value.strip().lower().replace(" ", "_")


class _ReadableHTMLParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1
        if tag.lower() in {"p", "br", "li", "tr", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag.lower() in {"p", "li", "tr", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def _normalize_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(content))
    except Exception:
        return ""
    pages: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            pages.append(text)
    return _normalize_text("\n".join(pages))
