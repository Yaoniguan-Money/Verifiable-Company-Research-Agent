"""重排序：默认词面重叠（CPU），可选 ONNX cross-encoder。"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.providers.embedding.base import EmbeddingProvider

DEFAULT_RERANK_TOP_K = 8
_CROSS_ENCODER_MAX_LENGTH = 512


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{2,}", text.lower()))


def _effective_top_k(top_k: int, size: int) -> int:
    """top_k 来自配置或调用方，先收口，避免负数切片返回错误结果。"""
    return min(max(top_k, 0), size)


class Reranker(ABC):
    @abstractmethod
    def rerank(
        self, query: str, chunks: list[str], *, top_k: int = DEFAULT_RERANK_TOP_K
    ) -> list[tuple[int, float]]:
        """返回 (原下标, 分数) 列表，按分数降序。"""


class LexicalReranker(Reranker):
    """无模型依赖的重排，适合 CI 与无 GPU 环境。"""

    def rerank(
        self, query: str, chunks: list[str], *, top_k: int = DEFAULT_RERANK_TOP_K
    ) -> list[tuple[int, float]]:
        limit = _effective_top_k(top_k, len(chunks))
        if limit == 0:
            return []
        q_tokens = _tokenize(query)
        if not q_tokens:
            return [(idx, 0.0) for idx in range(limit)]
        scored: list[tuple[int, float]] = []
        for idx, chunk in enumerate(chunks):
            c_tokens = _tokenize(chunk)
            if not c_tokens:
                scored.append((idx, 0.0))
                continue
            overlap = len(q_tokens & c_tokens) / max(len(q_tokens), 1)
            scored.append((idx, float(overlap)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


@dataclass
class OnnxRerankerConfig:
    model_name: str = "BAAI/bge-reranker-base"


class OnnxReranker(Reranker):
    """可选 ONNX 重排；依赖未安装时抛 ImportError。"""

    def __init__(self, config: OnnxRerankerConfig | None = None) -> None:
        self.config = config or OnnxRerankerConfig()
        from optimum.onnxruntime import ORTModelForSequenceClassification  # noqa: PLC0415
        from transformers import AutoTokenizer  # noqa: PLC0415

        self.tokenizer = AutoTokenizer.from_pretrained(self.config.model_name)
        self.model = ORTModelForSequenceClassification.from_pretrained(
            self.config.model_name,
            export=True,
            provider="CPUExecutionProvider",
        )

    def rerank(
        self, query: str, chunks: list[str], *, top_k: int = DEFAULT_RERANK_TOP_K
    ) -> list[tuple[int, float]]:
        limit = _effective_top_k(top_k, len(chunks))
        if limit == 0:
            return []
        pairs = [[query, chunk] for chunk in chunks]
        inputs = self.tokenizer(
            pairs,
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=_CROSS_ENCODER_MAX_LENGTH,
        )
        outputs = self.model(**inputs)
        logits = outputs.logits.detach().cpu().numpy().reshape(-1)
        scored = [(idx, float(logits[idx])) for idx in range(len(chunks))]
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]


class EmbeddingReranker(Reranker):
    """Semantic reranking using the configured Embedding API.

    Reuses the existing EmbeddingProvider (DashScope / SiliconFlow / etc.)
    instead of requiring a separate cross-encoder model. No new dependencies.
    """

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    def rerank(
        self, query: str, chunks: list[str], *, top_k: int = DEFAULT_RERANK_TOP_K
    ) -> list[tuple[int, float]]:
        limit = _effective_top_k(top_k, len(chunks))
        if limit == 0:
            return []
        query_vec = self._provider.embed_query(query)
        chunk_vecs = self._provider.embed_documents(chunks)
        scored = [
            (idx, self._cosine(query_vec, chunk_vecs[idx]))
            for idx in range(len(chunks))
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        num = sum(x * y for x, y in zip(a, b, strict=False))
        na = (sum(x * x for x in a)) ** 0.5
        nb = (sum(y * y for y in b)) ** 0.5
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(num / (na * nb))


def build_reranker(backend: str, **kwargs: object) -> Reranker:
    backend = backend.strip().lower()
    if backend == "onnx":
        return OnnxReranker()
    if backend == "embedding":
        provider = kwargs.get("embedding_provider")
        if provider is None:
            raise ValueError("embedding_provider is required when reranker_backend=embedding")
        return EmbeddingReranker(provider)
    return LexicalReranker()
