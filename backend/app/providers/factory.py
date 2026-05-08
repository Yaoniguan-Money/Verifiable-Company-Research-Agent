from __future__ import annotations

from typing import Literal

from app.core.config import Settings, get_settings
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
from app.vectorstores import InMemoryVectorStore, SQLiteVectorStore, VectorStore


class ProviderFactory:
    """Strict provider selection for LLM/search/embedding/vector-store.

    Supports mock/dev providers and real providers (DeepSeek, Baidu AI Search,
    DashScope embedding) without implicit fallback between them.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        # Missing real-provider keys fail at construction time. We do not silently
        # switch to mock/local providers because that would invalidate real-chain checks.
        self.settings.validate_runtime_provider_requirements()

    def create_llm_provider(self) -> LLMProvider:
        if self.settings.llm_provider == "mock":
            return MockLLMProvider()
        if self.settings.llm_provider == "deepseek":
            return DeepSeekLLMProvider(
                api_key=self._deepseek_api_key(),
                base_url=self.settings.deepseek_base_url,
                model=self.settings.deepseek_model,
                timeout_seconds=self.settings.deepseek_timeout_seconds,
            )
        if self.settings.llm_provider == "qianfan":
            return QianfanLLMProvider(
                api_key=self._qianfan_api_key(),
                base_url=self.settings.qianfan_base_url,
                model=self.settings.qianfan_model,
                timeout_seconds=self.settings.qianfan_timeout_seconds,
            )
        raise ValueError(f"Unsupported LLM provider: {self.settings.llm_provider}")

    def create_search_provider(self) -> SearchProvider:
        if self.settings.search_provider == "mock":
            return MockSearchProvider()
        if self.settings.search_provider == "local_documents":
            return LocalDocumentSearchProvider(self.settings.local_documents_dir)
        if self.settings.search_provider == "official_urls":
            return OfficialUrlSearchProvider(
                root_dir=self.settings.local_documents_dir,
                allowed_domains=self.settings.official_url_domain_list,
                timeout_seconds=self.settings.official_url_timeout_seconds,
            )
        if self.settings.search_provider == "baidu_ai_search":
            return self._create_baidu_ai_search_provider()
        if self.settings.search_provider == "cninfo_announcements":
            return CninfoAnnouncementProvider(
                timeout_seconds=self.settings.cninfo_timeout_seconds,
                top_k=self.settings.cninfo_top_k,
                lookback_years=self.settings.cninfo_lookback_years,
                max_source_chars=self.settings.cninfo_max_source_chars,
            )
        if self.settings.search_provider == "public_sources":
            providers: list[SearchProvider] = [
                CninfoAnnouncementProvider(
                    timeout_seconds=self.settings.cninfo_timeout_seconds,
                    top_k=self.settings.cninfo_top_k,
                    lookback_years=self.settings.cninfo_lookback_years,
                    max_source_chars=self.settings.cninfo_max_source_chars,
                )
            ]
            if self.settings.has_baidu_ai_search_api_key:
                providers.append(self._create_baidu_ai_search_provider())
            return HybridPublicSearchProvider(providers)
        raise ValueError(f"Unsupported search provider: {self.settings.search_provider}")

    def create_embedding_provider(self) -> EmbeddingProvider:
        # mock/local_hashing are explicit dev/test choices. Real semantic validation
        # should use dashscope unless a compatible provider is separately verified.
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
        raise ValueError(f"Unsupported vector store: {self.settings.vector_store}")

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
            endpoint=self.settings.baidu_ai_search_endpoint,
            model=self.settings.baidu_ai_search_model,
            top_k=self.settings.baidu_ai_search_top_k,
            timeout_seconds=self.settings.baidu_ai_search_timeout_seconds,
            fetch_reference_pages=self.settings.baidu_ai_search_fetch_reference_pages,
            enable_deep_search=self.settings.baidu_ai_search_enable_deep_search,
            allowed_domains=self.settings.official_url_domain_list,
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
