from __future__ import annotations

import pytest
from app.core.config import Settings
from app.providers.embedding import LocalHashingEmbeddingProvider, MockEmbeddingProvider
from app.providers.factory import ProviderFactory
from app.providers.llm import MockLLMProvider
from app.providers.qianfan_llm_provider import QianfanLLMProvider
from pydantic import ValidationError


def test_settings_provider_name_strip_and_lower() -> None:
    settings = Settings(
        llm_provider=" qianfan ",
        search_provider=" BAIDU_AI_SEARCH ",
        embedding_provider=" Local_Hashing ",
        qianfan_api_key="unit-test-key",
        baidu_ai_search_api_key="unit-test-key",
    )

    assert settings.llm_provider == "qianfan"
    assert settings.search_provider == "baidu_ai_search"
    assert settings.embedding_provider == "local_hashing"


def test_settings_rejects_invalid_llm_provider() -> None:
    with pytest.raises(ValueError):
        Settings(llm_provider="abc")


def test_settings_requires_qianfan_key_when_selected() -> None:
    with pytest.raises(ValueError, match="QIANFAN_API_KEY"):
        settings = Settings(llm_provider="qianfan", qianfan_api_key="")
        settings.validate_runtime_provider_requirements()


def test_explicit_mock_only_uses_mock_llm() -> None:
    factory = ProviderFactory(Settings(llm_provider="mock"))
    assert isinstance(factory.create_llm_provider(), MockLLMProvider)


def test_embedding_local_hashing_does_not_return_mock() -> None:
    factory = ProviderFactory(Settings(embedding_provider="local_hashing"))
    provider = factory.create_embedding_provider()
    assert isinstance(provider, LocalHashingEmbeddingProvider)
    assert not isinstance(provider, MockEmbeddingProvider)


def test_settings_rejects_invalid_embedding_provider() -> None:
    with pytest.raises(ValidationError):
        Settings(embedding_provider="not_supported")


def test_validate_runtime_requires_embedding_key_for_dashscope() -> None:
    s = Settings(
        embedding_provider="dashscope",
        embedding_api_key=None,
        llm_provider="mock",
        search_provider="mock",
    )
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        s.validate_runtime_provider_requirements()


def test_validate_runtime_requires_embedding_key_for_siliconflow() -> None:
    s = Settings(
        embedding_provider="siliconflow",
        embedding_api_key="",
        llm_provider="mock",
        search_provider="mock",
    )
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        s.validate_runtime_provider_requirements()


def test_qianfan_provider_selected_explicitly() -> None:
    factory = ProviderFactory(
        Settings(
            llm_provider="qianfan",
            qianfan_api_key="unit-test-key",
        )
    )
    assert isinstance(factory.create_llm_provider(), QianfanLLMProvider)
