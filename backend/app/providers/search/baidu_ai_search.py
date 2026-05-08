from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from app.providers.search.baidu_reference import BaiduReferenceProcessor
from app.providers.search.base import SearchProvider
from app.schemas.common import (
    SOURCE_LAYER_METADATA_KEY,
    SourceAuthority,
    authority_label,
    source_layer_priority,
)
from app.schemas.source import SourceCreate
from pydantic import SecretStr

logger = logging.getLogger(__name__)


class BaiduAISearchProvider(SearchProvider):
    """百度 AI 搜索 provider。

    用百度搜索返回候选引用，再尽量抓取引用 URL 正文；抓取失败时才回退到引用摘要。
    注意：它是“真实可用的公开资料入口”，不是稳定权威来源检索系统，来源质量仍需持续优化。
    """

    def __init__(
        self,
        *,
        api_key: SecretStr | str,
        endpoint: str = "https://qianfan.baidubce.com/v2/ai_search/chat/completions",
        model: str = "ernie-4.5-turbo-32k",
        top_k: int = 5,
        timeout_seconds: float = 30.0,
        fetch_reference_pages: bool = True,
        enable_deep_search: bool = False,
        allowed_domains: list[str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        self.endpoint = endpoint
        self.model = model
        self.top_k = top_k
        self.timeout_seconds = timeout_seconds
        self.fetch_reference_pages = fetch_reference_pages
        self.enable_deep_search = enable_deep_search
        self.allowed_domains = [item.strip().lower() for item in allowed_domains or [] if item.strip()]
        self._client = client

    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        client = self._client or httpx.Client(timeout=self.timeout_seconds, follow_redirects=True)
        should_close = self._client is None
        payload = self._payload(company_name=company_name, question=question)
        query = str(payload["messages"][0]["content"])
        logger.info("Baidu AI Search query preview: %s", query[:300])
        try:
            response = client.post(
                self.endpoint,
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            logger.info("Baidu AI Search response keys: %s", list(data.keys()))
            references = data.get("references") or []
            logger.info("Baidu AI Search raw references count: %s", len(references))
            for idx, item in enumerate(references[:3], start=1):
                if not isinstance(item, dict):
                    continue
                logger.info(
                    "Baidu AI Search reference #%s: title=%s url=%s type=%s",
                    idx,
                    item.get("title") or item.get("web_anchor"),
                    item.get("url"),
                    item.get("type"),
                )
            processor = BaiduReferenceProcessor(
                company_name=company_name,
                allowed_domains=self.allowed_domains,
                fetch_reference_pages=self.fetch_reference_pages,
            )
            sources = processor.sources_from_references(
                client=client,
                references=references,
                now=datetime.now(timezone.utc),
            )
            sources, official_disclosure_count, fallback_count = processor.augment_with_official_sources_if_needed(
                client=client,
                sources=sources,
                now=datetime.now(timezone.utc),
            )
            if official_disclosure_count or fallback_count:
                logger.info(
                    "Baidu AI Search source quality insufficient; official disclosures added=%s fallback entries added=%s",
                    official_disclosure_count,
                    fallback_count,
                )
            sources = sorted(
                sources,
                key=lambda item: (
                    source_layer_priority((item.source_metadata or {}).get(SOURCE_LAYER_METADATA_KEY)),
                    item.credibility_score or 0,
                ),
                reverse=True,
            )
            logger.info("Baidu AI Search source candidates count: %s", len(sources))
            high_authority = [
                s for s in sources if authority_label(s.credibility_score) == SourceAuthority.HIGH
            ]
            low_authority = [
                s for s in sources if authority_label(s.credibility_score) == SourceAuthority.LOW
            ]
            logger.info(
                "Baidu AI Search quality summary: high_authority=%s low_authority=%s",
                len(high_authority),
                len(low_authority),
            )
        finally:
            if should_close:
                client.close()

        if not sources:
            raise ValueError("Baidu AI search returned no usable references")
        return sources

    def _headers(self) -> dict[str, str]:
        token = self.api_key if self.api_key.lower().startswith("bearer ") else f"Bearer {self.api_key}"
        # 百度文档示例同时出现 Authorization 与 X-Appbuilder-Authorization；两者都发，兼容性更稳。
        return {
            "Authorization": token,
            "X-Appbuilder-Authorization": token,
            "Content-Type": "application/json",
        }

    def _payload(self, *, company_name: str, question: str) -> dict[str, object]:
        query = (
            f"公司名称：{company_name}\n"
            f"研究问题：{question}\n"
            "请检索该公司的公开资料，优先使用：公司官网、港交所/上交所/深交所公告、"
            "交易所公告、年报、半年报、监管披露、官方新闻稿。"
            "重点关注：最近三年经营风险、收入结构、研发投入、净利润、公开披露一致性。"
            "不要返回投资建议、股票推荐、培训资料、考试题、无关新闻、百科问答。"
        )
        instruction = (
            "你是企业公开信息检索助手。"
            "只围绕指定公司检索公开可信来源。"
            "优先返回公司官网、交易所公告、年报、半年报、监管披露。"
            "必须尽量返回带 URL 的引用来源。"
            "不要返回投资建议、股票推荐、考试题、问答平台闲聊内容或无关网页。"
        )
        return {
            "messages": [{"role": "user", "content": query}],
            "stream": False,
            "model": self.model,
            "search_source": "baidu_search_v2",
            "search_mode": "required",
            "resource_type_filter": [{"type": "web", "top_k": self.top_k}],
            "enable_deep_search": self.enable_deep_search,
            "enable_followup_queries": False,
            "enable_corner_markers": True,
            "enable_reasoning": False,
            "instruction": instruction,
            "temperature": 0.1,
            "top_p": 0.5,
            "max_completion_tokens": 1024,
            "max_refer_search_items": self.top_k,
        }
