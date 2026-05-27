"""Mock 向量：本地确定性算法，不访问网络、不读环境变量、不要 API key。"""

from __future__ import annotations

import hashlib
from math import cos, sin

from app.providers.embedding.base import EmbeddingProvider


class MockEmbeddingProvider(EmbeddingProvider):
    """对 UTF-8 文本做可重复哈希，展开为低维实向量 + 可落库 ``embedding_id`` 指纹。"""

    def __init__(self, *, dimension: int = 8) -> None:
        if dimension < 1:
            raise ValueError("dimension 须 >= 1")
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def _normalized_text(self, text: str) -> str:
        s = (text or "").strip()
        if not s:
            raise ValueError("仅空白或空字符串无法生成向量")
        return s

    def _digest(self, s: str) -> bytes:
        return hashlib.sha256(s.encode("utf-8")).digest()

    def _vector_for_digest(self, digest: bytes) -> list[float]:
        d = int(self._dim)
        out: list[float] = []
        for i in range(d):
            b0 = digest[i % len(digest)]
            b1 = digest[(i + 1) % len(digest)]
            t = 2.0 * 3.141592 * (b0 * 256 + b1) / 65535.0
            v = 0.5 * sin(t) + 0.5 * cos(2.0 * t) * (b0 / 255.0 - 0.5)
            out.append(round(v, 6))
        return out

    def embed_query(self, text: str) -> list[float]:
        s = self._normalized_text(text)
        return self._vector_for_digest(self._digest(s))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for t in texts:
            out.append(self.embed_query(t))
        return out

    def embedding_id_for_text(self, text: str) -> str:
        s = self._normalized_text(text)
        h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
        return f"mock-emb-v1-dim{self._dim}-{h}"
