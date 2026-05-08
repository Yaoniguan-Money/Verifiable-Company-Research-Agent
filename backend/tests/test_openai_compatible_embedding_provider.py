"""OpenAI-compatible embedding provider 单元测试（httpx 打桩）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from app.providers.embedding.openai_compatible_provider import (
    EmbeddingUpstreamError,
    OpenAICompatibleEmbeddingProvider,
)


def _http_client_cm(mock_inner: MagicMock) -> MagicMock:
    mgr = MagicMock()
    mgr.__enter__.return_value = mock_inner
    mgr.__exit__.return_value = None
    return mgr


def test_openai_compatible_embed_query_parses_response() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": [{"object": "embedding", "embedding": [0.25, -0.1, 0.0], "index": 0}]
    }

    inner = MagicMock()
    inner.post.return_value = resp

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="test-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="text-embedding-v4",
        )
        vec = p.embed_query("你好世界")

    assert vec == [0.25, -0.1, 0.0]
    assert len(vec) == 3
    assert p.dimension == 3

    inner.post.assert_called_once()
    call_kw = inner.post.call_args
    assert str(call_kw[0][0]).endswith("/embeddings")


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        (
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
        ),
        (
            "https://api.siliconflow.cn/v1/",
            "https://api.siliconflow.cn/v1/embeddings",
        ),
        (
            "https://example.com/v1/embeddings",
            "https://example.com/v1/embeddings",
        ),
    ],
)
def test_openai_compatible_endpoint_appends_embeddings_once(
    base_url: str, expected: str
) -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": [{"embedding": [0.1, 0.2], "index": 0}]}
    inner = MagicMock()
    inner.post.return_value = resp

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url=base_url,
            model="m",
        )
        p.embed_query("x")

    assert inner.post.call_args.args[0] == expected
    assert "/v1/v1/embeddings" not in inner.post.call_args.args[0]


def test_openai_compatible_embed_documents_empty_returns_empty() -> None:
    p = OpenAICompatibleEmbeddingProvider(
        provider_key="dashscope",
        api_key="k",
        base_url="https://example.com/v1",
        model="m",
    )
    assert p.embed_documents([]) == []


def test_openai_compatible_single_item_makes_one_request() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": [{"embedding": [0.1, 0.2], "index": 0}]}
    inner = MagicMock()
    inner.post.return_value = resp
    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
            max_batch_size=10,
        )
        out = p.embed_documents(["a"])
    assert len(out) == 1
    assert inner.post.call_count == 1


def test_openai_compatible_ten_items_makes_one_request() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": [{"embedding": [float(i), float(i + 1)], "index": i} for i in range(10)]
    }
    inner = MagicMock()
    inner.post.return_value = resp
    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
            max_batch_size=10,
        )
        out = p.embed_documents([f"t{i}" for i in range(10)])
    assert len(out) == 10
    assert inner.post.call_count == 1


def test_openai_compatible_eleven_items_split_into_10_and_1() -> None:
    def _payload_for(n: int) -> dict[str, list[dict[str, object]]]:
        return {"data": [{"embedding": [float(i), 0.0], "index": i} for i in range(n)]}

    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = _payload_for(10)
    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = _payload_for(1)
    inner = MagicMock()
    inner.post.side_effect = [resp1, resp2]

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
            max_batch_size=10,
        )
        out = p.embed_documents([f"t{i}" for i in range(11)])
    assert len(out) == 11
    assert inner.post.call_count == 2
    first_input = inner.post.call_args_list[0].kwargs["json"]["input"]
    second_input = inner.post.call_args_list[1].kwargs["json"]["input"]
    assert len(first_input) == 10
    assert len(second_input) == 1


def test_openai_compatible_twenty_three_items_split_into_10_10_3() -> None:
    def _resp(n: int) -> MagicMock:
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {"data": [{"embedding": [1.0, 0.0], "index": i} for i in range(n)]}
        return r

    inner = MagicMock()
    inner.post.side_effect = [_resp(10), _resp(10), _resp(3)]

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
            max_batch_size=10,
        )
        out = p.embed_documents([f"t{i}" for i in range(23)])
    assert len(out) == 23
    assert inner.post.call_count == 3
    sizes = [len(call.kwargs["json"]["input"]) for call in inner.post.call_args_list]
    assert sizes == [10, 10, 3]


def test_openai_compatible_multi_batch_result_order_matches_input() -> None:
    def _resp(start: int, n: int) -> MagicMock:
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {
            "data": [
                {"embedding": [float(start + i), 0.0], "index": i}
                for i in range(n)
            ]
        }
        return r

    inner = MagicMock()
    inner.post.side_effect = [_resp(0, 10), _resp(10, 1)]

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
            max_batch_size=10,
        )
        out = p.embed_documents([f"t{i}" for i in range(11)])
    assert [v[0] for v in out] == [float(i) for i in range(11)]


def test_openai_compatible_batch_failure_in_second_request_raises() -> None:
    ok = MagicMock()
    ok.status_code = 200
    ok.json.return_value = {"data": [{"embedding": [0.1, 0.2], "index": 0} for _ in range(10)]}
    fail = MagicMock()
    fail.status_code = 500
    fail.text = "boom"
    inner = MagicMock()
    inner.post.side_effect = [ok, fail]

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
            max_batch_size=10,
        )
        with pytest.raises(EmbeddingUpstreamError, match="500"):
            p.embed_documents([f"t{i}" for i in range(11)])


def test_openai_compatible_max_batch_size_le_zero_raises() -> None:
    with pytest.raises(ValueError, match="EMBEDDING_MAX_BATCH_SIZE"):
        OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
            max_batch_size=0,
        )


def test_openai_compatible_embed_documents_batch_ordered_by_index() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": [
            {"embedding": [1.0, 0.0], "index": 1},
            {"embedding": [0.0, 1.0], "index": 0},
        ]
    }
    inner = MagicMock()
    inner.post.return_value = resp

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="siliconflow",
            api_key="k",
            base_url="https://api.siliconflow.cn/v1",
            model="BAAI/bge-m3",
        )
        out = p.embed_documents(["乙", "甲"])

    assert len(out) == 2
    assert out[0] == [0.0, 1.0]
    assert out[1] == [1.0, 0.0]


def test_openai_compatible_embedding_dimension_mismatch_with_config() -> None:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": [{"embedding": [0.1, 0.2], "index": 0}]}
    inner = MagicMock()
    inner.post.return_value = resp

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
            embedding_dimension=5,
        )
        with pytest.raises(EmbeddingUpstreamError, match="EMBEDDING_DIMENSION"):
            p.embed_query("x")


@pytest.mark.parametrize(
    "status,msg",
    [
        (401, "401"),
        (429, "429"),
        (500, "500"),
    ],
)
def test_openai_compatible_http_errors_raise(status: int, msg: str) -> None:
    resp = MagicMock()
    resp.status_code = status
    resp.text = "err-body"
    inner = MagicMock()
    inner.post.return_value = resp

    with patch(
        "app.providers.embedding.openai_compatible_provider.httpx.Client",
        return_value=_http_client_cm(inner),
    ):
        p = OpenAICompatibleEmbeddingProvider(
            provider_key="dashscope",
            api_key="k",
            base_url="https://example.com/v1",
            model="m",
        )
        with pytest.raises(EmbeddingUpstreamError, match=msg):
            p.embed_query("t")


def test_embedding_id_fingerprint_not_full_text() -> None:
    p = OpenAICompatibleEmbeddingProvider(
        provider_key="dashscope",
        api_key="k",
        base_url="https://example.com/v1",
        model="text-embedding-v4",
    )
    long_text = "长文本" * 80
    eid = p.embedding_id_for_text(long_text)
    assert len(eid) <= 128
    assert long_text not in eid
