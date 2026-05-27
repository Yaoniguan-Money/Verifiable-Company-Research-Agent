"""Provider 工厂：根据 ``Settings`` 装配 LLM / Search / Embedding / 向量存储。

设计取舍
--------
- **严格选型**：实例化时立即调用 ``validate_runtime_provider_requirements``，
  缺 key 立刻 ``ValueError``。绝不静默回退到 mock，否则真实链路验证会失真。
- **mock / local 仅供 dev/test**：所有"无 key 即可用"的 provider 必须显式选择，
  不会因为没填密钥就自动走 mock 路径。
- **搜索默认缓存**：除 ``mock`` 外，所有 search provider 都会被 ``CachedSearchProvider``
  包一层，Redis 不可用时自动透传，不阻断业务。
"""

from __future__ import annotations

from typing import Literal

from app.core.config import Settings, get_settings
from app.infra.redis_cache import get_redis_cache
from app.providers.embedding import (
    EmbeddingProvider,
    LocalHashingEmbeddingProvider,
    MockEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.providers.llm import DeepSeekLLMProvider, LLMProvider, MockLLMProvider
from app.providers.qianfan_llm_provider import QianfanLLMProvider
from app.providers.search import (
    BaiduAISearchProvider,
    CninfoAnnouncementProvider,
    HybridPublicSearchProvider,
    LocalDocumentSearchProvider,
    MockSearchProvider,
    OfficialUrlSearchProvider,
    SearchProvider,
)
from app.providers.search.cached import CachedSearchProvider
from app.services.content_enrichment import (
    ContentEnrichmentPipeline,
    FinancialReportEnricher,
    PDFCache,
    SectionAnnotator,
    TableMarkdownEnricher,
)
from app.vectorstores import InMemoryVectorStore, PgVectorStore, SQLiteVectorStore, VectorStore


class ProviderFactory:
    """根据配置选择具体 provider 实现。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        # 缺 key 在构造期立刻报错，避免后续业务跑到一半才发现。
        self.settings.validate_runtime_provider_requirements()

    def create_llm_provider(self) -> LLMProvider:
        if self.settings.llm_provider == "mock":
            return MockLLMProvider()
        if self.settings.llm_provider == "deepseek":
            return DeepSeekLLMProvider(
                api_key=self._deepseek_api_key(),
                base_url=self.settings.resolved_deepseek_base_url,
                model=self.settings.resolved_deepseek_model,
                timeout_seconds=self.settings.deepseek_timeout_seconds,
            )
        if self.settings.llm_provider == "qianfan":
            return QianfanLLMProvider(
                api_key=self._qianfan_api_key(),
                base_url=self.settings.resolved_qianfan_base_url,
                model=self.settings.resolved_qianfan_model,
                timeout_seconds=self.settings.qianfan_timeout_seconds,
            )
        raise ValueError(f"Unsupported LLM provider: {self.settings.llm_provider}")

    def create_search_provider(self) -> SearchProvider:
        if self.settings.search_provider == "mock":
            return MockSearchProvider()
        if self.settings.search_provider == "local_documents":
            return self._maybe_wrap_search_cache(
                LocalDocumentSearchProvider(self.settings.local_documents_dir)
            )
        if self.settings.search_provider == "official_urls":
            return self._maybe_wrap_search_cache(
                OfficialUrlSearchProvider(
                    root_dir=self.settings.local_documents_dir,
                    allowed_domains=self.settings.official_url_domain_list,
                    timeout_seconds=self.settings.official_url_timeout_seconds,
                )
            )
        if self.settings.search_provider == "baidu_ai_search":
            return self._maybe_wrap_search_cache(
                HybridPublicSearchProvider(
                    [
                        self._create_cninfo_announcement_provider(),
                        self._create_baidu_ai_search_provider(),
                    ]
                )
            )
        if self.settings.search_provider == "cninfo_announcements":
            return self._maybe_wrap_search_cache(self._create_cninfo_announcement_provider())
        if self.settings.search_provider == "public_sources":
            providers: list[SearchProvider] = [self._create_cninfo_announcement_provider()]
            if self.settings.has_baidu_ai_search_api_key:
                providers.append(self._create_baidu_ai_search_provider())
            provider = HybridPublicSearchProvider(providers)
            return self._maybe_wrap_search_cache(provider)
        raise ValueError(f"Unsupported search provider: {self.settings.search_provider}")

    def _maybe_wrap_search_cache(self, provider: SearchProvider) -> SearchProvider:
        cache = get_redis_cache()
        if not cache.enabled:
            return provider
        return CachedSearchProvider(
            provider,
            cache=cache,
            ttl_seconds=self.settings.search_cache_ttl_seconds,
        )

    def create_embedding_provider(self) -> EmbeddingProvider:
        # mock / local_hashing 仅供 dev/test 验证管线连通性，不要在真实语义检索时使用。
        if self.settings.embedding_provider == "mock":
            return MockEmbeddingProvider(dimension=self.settings.mock_embedding_dimension)
        if self.settings.embedding_provider == "local_hashing":
            return LocalHashingEmbeddingProvider(dimension=self.settings.local_embedding_dimension)
        if self.settings.embedding_provider == "dashscope":
            return self._create_openai_compatible_embedding_provider("dashscope")
        if self.settings.embedding_provider == "siliconflow":
            return self._create_openai_compatible_embedding_provider("siliconflow")
        raise ValueError(f"Unsupported embedding provider: {self.settings.embedding_provider}")

    def create_vector_store(self) -> VectorStore:
        if self.settings.vector_store == "in_memory":
            return InMemoryVectorStore()
        if self.settings.vector_store == "sqlite":
            return SQLiteVectorStore(self.settings.vector_store_sqlite_path)
        if self.settings.vector_store == "pgvector":
            return PgVectorStore(self.settings.database_url)
        raise ValueError(f"Unsupported vector store: {self.settings.vector_store}")

    def create_content_enrichment_pipeline(self) -> ContentEnrichmentPipeline:
        stages: list = []
        if not self.settings.content_enrichment_enabled:
            # 工厂方法也尊重总开关，避免绕过上层调用方时意外启用增强链。
            return ContentEnrichmentPipeline(stages)
        if self.settings.pdf_cache_enabled:
            stages.append(PDFCache(
                cache_dir=self.settings.pdf_cache_dir,
                max_size_mb=self.settings.pdf_cache_max_size_mb,
                ttl_hours=self.settings.pdf_cache_ttl_hours,
            ))
        stages.append(FinancialReportEnricher(
            max_sections=self.settings.report_parser_max_sections,
            max_tables=self.settings.table_extraction_max_tables,
        ))
        stages.append(TableMarkdownEnricher(
            max_tables=self.settings.table_extraction_max_tables,
        ))
        stages.append(SectionAnnotator())
        return ContentEnrichmentPipeline(stages)

    def _deepseek_api_key(self) -> str:
        if not self.settings.has_deepseek_api_key or self.settings.deepseek_api_key is None:
            raise ValueError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek")
        return self.settings.deepseek_api_key.get_secret_value()

    def _qianfan_api_key(self) -> str:
        if not self.settings.has_qianfan_api_key or self.settings.qianfan_api_key is None:
            raise ValueError("QIANFAN_API_KEY is required when LLM_PROVIDER=qianfan")
        return self.settings.qianfan_api_key.get_secret_value()

    def _create_baidu_ai_search_provider(self) -> BaiduAISearchProvider:
        if not self.settings.has_baidu_ai_search_api_key:
            raise ValueError(
                "BAIDU_AI_SEARCH_API_KEY is required when SEARCH_PROVIDER=baidu_ai_search"
            )
        assert self.settings.baidu_ai_search_api_key is not None
        return BaiduAISearchProvider(
            api_key=self.settings.baidu_ai_search_api_key,
            endpoint=self.settings.resolved_baidu_ai_search_endpoint,
            model=self.settings.resolved_baidu_ai_search_model,
            top_k=self.settings.baidu_ai_search_top_k,
            timeout_seconds=self.settings.baidu_ai_search_timeout_seconds,
            fetch_reference_pages=self.settings.baidu_ai_search_fetch_reference_pages,
            enable_deep_search=self.settings.baidu_ai_search_enable_deep_search,
            allowed_domains=self.settings.official_url_domain_list,
        )

    def _create_cninfo_announcement_provider(self) -> CninfoAnnouncementProvider:
        return CninfoAnnouncementProvider(
            timeout_seconds=self.settings.cninfo_timeout_seconds,
            top_k=self.settings.cninfo_top_k,
            lookback_years=self.settings.cninfo_lookback_years,
            max_source_chars=self.settings.cninfo_max_source_chars,
        )

    def _embedding_api_key(self, provider_key: str) -> str:
        if not self.settings.has_embedding_api_key or self.settings.embedding_api_key is None:
            raise ValueError(f"EMBEDDING_API_KEY is required when EMBEDDING_PROVIDER={provider_key}")
        return self.settings.embedding_api_key.get_secret_value()

    def _create_openai_compatible_embedding_provider(
        self, provider_key: Literal["dashscope", "siliconflow"]
    ) -> OpenAICompatibleEmbeddingProvider:
        return OpenAICompatibleEmbeddingProvider(
            provider_key=provider_key,
            api_key=self._embedding_api_key(provider_key),
            base_url=self.settings.resolved_embedding_base_url or "",
            model=self.settings.resolved_embedding_model or "",
            timeout_seconds=self.settings.embedding_timeout_seconds,
            embedding_dimension=self.settings.embedding_dimension,
            max_batch_size=self.settings.embedding_max_batch_size,
        )
