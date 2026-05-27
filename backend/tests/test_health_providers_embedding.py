"""Provider health 与 embedding 元数据展示。"""

from __future__ import annotations

from app.core.config import get_settings


def test_providers_health_includes_embedding_fields(client) -> None:
    r = client.get("/api/health/providers")
    assert r.status_code == 200
    data = r.json()
    assert data["embedding_model"] == "mock"
    assert "embedding_api_key_configured" in data
    assert "embedding_base_url_configured" in data
    assert "embedding_base_url_host" in data
    assert "embedding_dimension_configured" in data
    assert "embedding_max_batch_size" in data
    assert data["search_mode"] == "mock"
    assert data["search_network_enabled"] is False
    assert data["embedding_max_batch_size"] == 10
    assert data["embedding_api_key_configured"] in (True, False)


def test_providers_health_dashscope_no_key_in_response(client, monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_PROVIDER", "dashscope")
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    get_settings.cache_clear()
    try:
        r = client.get("/api/health/providers")
        assert r.status_code == 200
        data = r.json()
        assert data["embedding_provider"] == "dashscope"
        assert data["embedding_api_key_configured"] is False
        assert data["embedding_model"] == "text-embedding-v4"
        assert data["embedding_base_url_host"] == "dashscope.aliyuncs.com"
    finally:
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")
        monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
        get_settings.cache_clear()
