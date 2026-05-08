"""Embedding Provider 抽象：仅生成向量，不涉及向量库与检索。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """可替换的文本向量提供者。

    **输入/输出**：
    - ``embed_query(text) -> list[float]``，长度为 ``dimension`` 的**浮点**列表。
    - ``embed_documents(texts) -> list[list[float]``，与 ``texts`` 一一对应。

    **空输入行为**（全阶段统一，实现类必须一致）：
    - ``embed_documents([])`` → 返回空列表 ``[]``（不抛错）。
    - ``embed_query("")``、或仅由空白/换行组成的字符串 → 抛出 ``ValueError``。
    - ``embed_documents`` 的列表中若含空串或**仅**空白/换行的项 → 抛出 ``ValueError``。

    **说明**：本层不负责写入数据库、不访问向量库、不做相似度搜索；2.B 仅由 ``EmbeddingService`` 等
    在业务侧将 ``embedding_id`` 指纹写入 ORM 列，不将 ``list[float]`` 长期塞进 ``chunk_metadata``。
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量固定维度，随实现确定。"""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """单条查询文本转向量。``text`` 经 ``strip()`` 后若为空则抛 ``ValueError``。"""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """多条文档转向量。``texts==[]`` 时返回 ``[]``；任一项为空白时抛 ``ValueError``。"""

    @abstractmethod
    def embedding_id_for_text(self, text: str) -> str:
        """为给定非空（strip 后）文本生成**确定性**的短字符串，用于 ``evidence_chunks.embedding_id``。

        同文本、同实现、同维度应得同一 ID；不序列化整段向量，仅作可落库指纹。
        """
