"""OpenAI-compatible HTTP embedding provider（DashScope / SiliconFlow 等兼容端点）。"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from app.providers.embedding.base import EmbeddingProvider


class EmbeddingUpstreamError(RuntimeError):
    """Embedding API 请求失败或返回非预期结构。"""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _embeddings_endpoint(base_url: str) -> str:
    """Return the OpenAI-compatible embeddings endpoint.

    Normal configs use a provider root such as ``.../v1``. If an operator supplies
    a full ``.../embeddings`` endpoint, keep it as-is instead of appending twice.
    """
    root = base_url.rstrip("/")
    if root.endswith("/embeddings"):
        return root
    return f"{root}/embeddings"


def _normalize_for_fingerprint(text: str) -> str:
    """与项目其它 embedding 实现一致：strip、空白折叠、小写；空则非法。"""
    normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalized:
        raise ValueError("text must not be blank")
    return normalized


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """调用 OpenAI-compatible ``POST /embeddings`` 的向量提供者。

    ``embedding_id`` 为可落库的**稳定索引指纹**（provider + model + 文本摘要），
    不代表语义向量永久不变；模型或服务商升级后同一文本的向量可能变化。
    """

    def __init__(
        self,
        *,
        provider_key: Literal["dashscope", "siliconflow"],
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 30.0,
        embedding_dimension: int | None = None,
        max_batch_size: int = 10,
    ) -> None:
        key = (api_key or "").strip()
        if not key:
            raise ValueError("EMBEDDING_API_KEY is required for OpenAI-compatible embedding")
        bu = (base_url or "").strip()
        if not bu:
            raise ValueError("EMBEDDING_BASE_URL is required for OpenAI-compatible embedding")
        md = (model or "").strip()
        if not md:
            raise ValueError("EMBEDDING_MODEL is required for OpenAI-compatible embedding")
        if max_batch_size <= 0:
            raise ValueError("EMBEDDING_MAX_BATCH_SIZE must be > 0")

        self._provider_key = provider_key
        self._api_key = key
        self._base_url = bu.rstrip("/")
        self._model = md
        self._timeout = float(timeout_seconds)
        self._configured_dim: int | None = embedding_dimension
        self._max_batch_size = int(max_batch_size)
        self._observed_dim: int | None = None
        self._endpoint = _embeddings_endpoint(self._base_url)

    @property
    def dimension(self) -> int:
        if self._configured_dim is not None:
            return self._configured_dim
        if self._observed_dim is not None:
            return self._observed_dim
        raise RuntimeError("尚未完成嵌入调用，dimension 不可用")

    def embed_query(self, text: str) -> list[float]:
        vecs = self.embed_documents([text])
        if not vecs:
            raise RuntimeError("embed_query 内部错误：空向量列表")
        return vecs[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        for i, t in enumerate(texts):
            s = (t or "").strip()
            if not s:
                raise ValueError(f"embed_documents 第 {i} 项文本为空或仅空白")
        out: list[list[float]] = []
        for start in range(0, len(texts), self._max_batch_size):
            batch = texts[start : start + self._max_batch_size]
            out.extend(self._embed_batch(batch))
        return out

    def embedding_id_for_text(self, text: str) -> str:
        norm = _normalize_for_fingerprint(text)
        model_digest = hashlib.sha256(self._model.encode("utf-8")).hexdigest()[:8]
        text_digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        tag = "ds" if self._provider_key == "dashscope" else "sf"
        # 不包含完整 model 名，仅用摘要；总长远小于 DB 128 限制。
        return f"oae-{tag}-m{model_digest}-{text_digest}"

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        payload: dict[str, Any] = {"model": self._model, "input": texts}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise EmbeddingUpstreamError(
                f"Embedding API 请求超时（>{self._timeout}s）: {self._endpoint}"
            ) from exc
        except httpx.RequestError as exc:
            raise EmbeddingUpstreamError(f"Embedding API 网络错误: {exc}") from exc

        sc = response.status_code
        if sc in (401, 403):
            raise EmbeddingUpstreamError(
                f"Embedding API 认证失败（HTTP {sc}），请检查 EMBEDDING_API_KEY 与端点是否匹配",
                status_code=sc,
            )
        if sc == 429:
            raise EmbeddingUpstreamError(
                "Embedding API 限流（HTTP 429），请稍后重试或降低并发",
                status_code=sc,
            )
        if sc >= 500:
            body_preview = (response.text or "")[:400]
            raise EmbeddingUpstreamError(
                f"Embedding API 服务端错误（HTTP {sc}）: {body_preview}",
                status_code=sc,
            )
        if sc >= 400:
            body_preview = (response.text or "")[:400]
            raise EmbeddingUpstreamError(
                f"Embedding API 请求失败（HTTP {sc}）: {body_preview}",
                status_code=sc,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise EmbeddingUpstreamError("Embedding API 返回非 JSON 正文") from exc

        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise EmbeddingUpstreamError("Embedding API 响应缺少 data 列表")

        parsed: list[tuple[int, list[float]]] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise EmbeddingUpstreamError(f"Embedding API data[{idx}] 类型错误")
            emb = item.get("embedding")
            if not isinstance(emb, list):
                raise EmbeddingUpstreamError(f"Embedding API data[{idx}].embedding 缺失或非数组")
            try:
                vec = [float(x) for x in emb]
            except (TypeError, ValueError) as exc:
                raise EmbeddingUpstreamError(f"Embedding API data[{idx}].embedding 含非数值") from exc
            ix = item.get("index")
            sort_key = int(ix) if isinstance(ix, int) else idx
            parsed.append((sort_key, vec))

        parsed.sort(key=lambda x: x[0])
        vectors = [v for _, v in parsed]
        if len(vectors) != len(texts):
            raise EmbeddingUpstreamError(
                f"Embedding API 返回条数与请求不一致：请求 {len(texts)}，得到 {len(vectors)}"
            )

        dim = len(vectors[0])
        if dim <= 0:
            raise EmbeddingUpstreamError("Embedding API 返回空向量")
        for j, vec in enumerate(vectors):
            if len(vec) != dim:
                raise EmbeddingUpstreamError(
                    f"Embedding API 返回向量维度不一致：索引 {j} 期望 {dim} 实际 {len(vec)}"
                )

        if self._configured_dim is not None and dim != self._configured_dim:
            raise EmbeddingUpstreamError(
                f"Embedding API 返回维度 {dim} 与配置的 EMBEDDING_DIMENSION={self._configured_dim} 不一致"
            )

        if self._configured_dim is None:
            if self._observed_dim is None:
                self._observed_dim = dim
            elif dim != self._observed_dim:
                raise EmbeddingUpstreamError(
                    f"Embedding API 向量维度不一致：已为 {self._observed_dim}，当前批次为 {dim}"
                )

        return vectors


def embedding_base_url_host(base_url: str | None) -> str | None:
    """仅从 base URL 抽取 host，供健康检查展示，不含 path/query。"""
    if not base_url or not str(base_url).strip():
        return None
    parsed = urlparse(str(base_url).strip())
    return parsed.hostname
