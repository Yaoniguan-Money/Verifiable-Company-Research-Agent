"""Search Provider 抽象接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas.source import SourceCreate


class SearchProvider(ABC):
    """公开信息检索接口。

    注意：Provider 只负责“检索候选来源”，不负责 workflow 编排。
    """

    @abstractmethod
    def search(self, company_name: str, question: str) -> list[SourceCreate]:
        """根据企业名与研究问题返回候选来源。"""
        raise NotImplementedError
