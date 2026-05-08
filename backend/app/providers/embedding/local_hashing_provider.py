"""Local hashing embedding provider.

This deterministic provider is suitable for offline demos and regression tests.
It tokenizes text and builds normalized lexical vectors locally, so it is more
useful than the mock hash provider, but it is not a production semantic model.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.providers.embedding.base import EmbeddingProvider


class LocalHashingEmbeddingProvider(EmbeddingProvider):
    """Build fixed-size lexical vectors without external API calls."""

    def __init__(self, *, dimension: int = 128) -> None:
        if dimension < 8:
            raise ValueError("dimension must be >= 8")
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def embed_query(self, text: str) -> list[float]:
        normalized = self._normalize_text(text)
        vector = [0.0] * self._dim
        for token in self._features(normalized):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "big") % self._dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 12) / 12.0
            vector[idx] += sign * weight

        norm = math.sqrt(sum(item * item for item in vector))
        if norm == 0.0:
            return vector
        return [round(item / norm, 6) for item in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [self.embed_query(item) for item in texts]

    def embedding_id_for_text(self, text: str) -> str:
        normalized = self._normalize_text(text)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
        return f"local-hash-v1-dim{self._dim}-{digest}"

    def _normalize_text(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        if not normalized:
            raise ValueError("text must not be blank")
        return normalized

    def _features(self, text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", text)
        features: list[str] = []
        features.extend(tokens)
        for i in range(max(len(tokens) - 1, 0)):
            features.append(f"{tokens[i]}_{tokens[i + 1]}")
        return features or [text]
