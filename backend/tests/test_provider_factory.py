from __future__ import annotations

import pytest
from app.core.config import Settings
from app.providers.embedding import (
    LocalHashingEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from app.providers.factory import ProviderFactory
from app.providers.llm import DeepSeekLLMProvider, MockLLMProvider
from app.providers.qianfan_llm_provider import QianfanLLMProvider
from app.providers.search import (
    CninfoAnnouncementProvider,
    HybridPublicSearchProvider,
    LocalDocumentSearchProvider,
    MockSearchProvider,
    OfficialUrlSearchProvider,
)
from app.providers.search.cached import CachedSearchProvider
from app.vectorstores import InMemoryVectorStore, SQLiteVectorStore


def _unwrap_cached(provider):
    return provider.inner if isinstance(provider, CachedSearchProvider) else provider


def test_provider_factory_defaults_to_online_public_search_and_local_embedding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEARCH_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    factory = ProviderFactory(
        Settings(
            llm_provider="mock",
            search_provider="public_sources",
            embedding_provider="local_hashing",
            baidu_ai_search_api_key=None,
        )
    )

    assert isinstance(factory.create_llm_provider(), MockLLMProvider)
    search_provider = _unwrap_cached(factory.create_search_provider())
    assert isinstance(search_provider, HybridPublicSearchProvider)
    assert [type(item).__name__ for item in search_provider.providers] == [
        "CninfoAnnouncementProvider"
    ]
    assert isinstance(factory.create_embedding_provider(), LocalHashingEmbeddingProvider)
    assert isinstance(factory.create_vector_store(), InMemoryVectorStore)


def test_provider_factory_can_create_explicit_mock_search_provider() -> None:
    factory = ProviderFactory(Settings(search_provider="mock"))

    assert isinstance(factory.create_search_provider(), MockSearchProvider)


def test_provider_factory_can_create_local_hashing_embedding_provider() -> None:
    factory = ProviderFactory(
        Settings(
            embedding_provider="local_hashing",
            local_embedding_dimension=64,
        )
    )

    provider = factory.create_embedding_provider()

    assert isinstance(provider, LocalHashingEmbeddingProvider)
    assert provider.dimension == 64


def test_provider_factory_can_create_sqlite_vector_store(tmp_path) -> None:
    factory = ProviderFactory(
        Settings(
            vector_store="sqlite",
            vector_store_sqlite_path=str(tmp_path / "vectors.sqlite"),
        )
    )

    assert isinstance(factory.create_vector_store(), SQLiteVectorStore)


def test_provider_factory_can_create_local_document_search_provider() -> None:
    factory = ProviderFactory(Settings(search_provider="local_documents"))

    assert isinstance(_unwrap_cached(factory.create_search_provider()), LocalDocumentSearchProvider)


def test_provider_factory_can_create_official_url_search_provider() -> None:
    factory = ProviderFactory(
        Settings(
            search_provider="official_urls",
            official_url_allowed_domains="example.com,example.org",
        )
    )

    assert isinstance(_unwrap_cached(factory.create_search_provider()), OfficialUrlSearchProvider)


def test_provider_factory_can_create_baidu_ai_search_provider_with_key() -> None:
    factory = ProviderFactory(
        Settings(
            search_provider="baidu_ai_search",
            baidu_ai_search_api_key="test-key",
        )
    )

    provider = _unwrap_cached(factory.create_search_provider())

    assert isinstance(provider, HybridPublicSearchProvider)
    assert [type(item).__name__ for item in provider.providers] == [
        "CninfoAnnouncementProvider",
        "BaiduAISearchProvider",
    ]


def test_provider_factory_can_create_cninfo_announcement_provider() -> None:
    factory = ProviderFactory(Settings(search_provider="cninfo_announcements"))

    assert isinstance(_unwrap_cached(factory.create_search_provider()), CninfoAnnouncementProvider)


def test_provider_factory_can_create_public_sources_provider_with_optional_baidu() -> None:
    factory = ProviderFactory(
        Settings(
            search_provider="public_sources",
            baidu_ai_search_api_key="test-key",
        )
    )

    assert isinstance(_unwrap_cached(factory.create_search_provider()), HybridPublicSearchProvider)


def test_public_sources_ignores_blank_optional_baidu_key() -> None:
    factory = ProviderFactory(
        Settings(
            search_provider="public_sources",
            baidu_ai_search_api_key="",
        )
    )

    provider = _unwrap_cached(factory.create_search_provider())

    assert isinstance(provider, HybridPublicSearchProvider)
    assert [type(item).__name__ for item in provider.providers] == ["CninfoAnnouncementProvider"]


def test_provider_factory_requires_baidu_ai_search_key() -> None:
    with pytest.raises(ValueError, match="BAIDU_AI_SEARCH_API_KEY"):
        ProviderFactory(Settings(search_provider="baidu_ai_search", baidu_ai_search_api_key=None))


def test_provider_factory_can_create_deepseek_provider_with_key() -> None:
    factory = ProviderFactory(
        Settings(
            llm_provider="deepseek",
            deepseek_api_key="test-key",
        )
    )

    assert isinstance(factory.create_llm_provider(), DeepSeekLLMProvider)


def test_provider_factory_requires_deepseek_key() -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        ProviderFactory(Settings(llm_provider="deepseek", deepseek_api_key=None))


def test_provider_factory_can_create_qianfan_provider_with_key() -> None:
    factory = ProviderFactory(
        Settings(
            llm_provider="qianfan",
            qianfan_api_key="unit-test-token",
        )
    )

    assert isinstance(factory.create_llm_provider(), QianfanLLMProvider)


def test_provider_factory_requires_qianfan_key() -> None:
    with pytest.raises(ValueError, match="QIANFAN_API_KEY"):
        ProviderFactory(Settings(llm_provider="qianfan", qianfan_api_key=None))


def test_provider_factory_can_create_dashscope_openai_compatible() -> None:
    factory = ProviderFactory(
        Settings(
            embedding_provider="dashscope",
            embedding_api_key="unit-emb-key",
            embedding_max_batch_size=7,
        )
    )
    p = factory.create_embedding_provider()
    assert isinstance(p, OpenAICompatibleEmbeddingProvider)
    assert p._max_batch_size == 7


def test_provider_factory_can_create_siliconflow_openai_compatible() -> None:
    factory = ProviderFactory(
        Settings(embedding_provider="siliconflow", embedding_api_key="unit-emb-key")
    )
    p = factory.create_embedding_provider()
    assert isinstance(p, OpenAICompatibleEmbeddingProvider)


def test_provider_factory_requires_embedding_key_for_dashscope() -> None:
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        ProviderFactory(Settings(embedding_provider="dashscope", embedding_api_key=None))


def test_provider_factory_requires_embedding_key_for_siliconflow() -> None:
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        ProviderFactory(Settings(embedding_provider="siliconflow", embedding_api_key=None))


def test_content_enrichment_pipeline_respects_disabled_flag() -> None:
    factory = ProviderFactory(Settings(content_enrichment_enabled=False))

    pipeline = factory.create_content_enrichment_pipeline()

    assert pipeline._stages == []
