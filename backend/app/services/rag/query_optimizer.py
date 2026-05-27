"""查询优化：原文 + 关键词 + 可选 LLM 改写。"""

from __future__ import annotations

import re
from collections import Counter

from app.providers.llm.base import LLMProvider

DEFAULT_KEYWORD_LIMIT = 8
MAX_DECOMPOSED_QUERIES = 3
MIN_DECOMPOSED_QUERY_CHARS = 6
COMPLEX_QUERY_MIN_CHARS = 40
COMPLEX_QUERY_MIN_QUESTION_MARKS = 2

QUESTION_STOP_WORDS = frozenset(
    {
        "的",
        "了",
        "和",
        "是",
        "在",
        "与",
        "及",
        "对",
        "什么",
        "如何",
        "哪些",
        "公司",
        "企业",
    }
)


def _tokenize(text: str) -> list[str]:
    try:
        import jieba  # type: ignore[import-untyped]

        return [t.strip() for t in jieba.lcut(text) if t.strip()]
    except ImportError:
        return [t for t in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{2,}", text) if t]


class QueryOptimizer:
    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def optimize(self, question: str, *, enable_llm_rewrite: bool = True) -> list[str]:
        q = question.strip()
        if not q:
            return []
        queries = [q]
        keywords = self.extract_keywords(q)
        if keywords:
            self._append_unique(queries, " ".join(keywords))
        if enable_llm_rewrite and self.llm_provider is not None:
            rewritten = self.llm_rewrite(q)
            if rewritten:
                self._append_unique(queries, rewritten)
        if self.is_complex(q):
            for sub in self.decompose(q):
                self._append_unique(queries, sub)
        return queries

    def extract_keywords(self, question: str, top_n: int = DEFAULT_KEYWORD_LIMIT) -> list[str]:
        tokens = _tokenize(question)
        if not tokens:
            return []
        filtered = [t for t in tokens if t not in QUESTION_STOP_WORDS and len(t) > 1]
        counts = Counter(filtered)
        return [word for word, _ in counts.most_common(top_n)]

    def llm_rewrite(self, question: str) -> str | None:
        if self.llm_provider is None:
            return None
        try:
            rewritten = self.llm_provider.rewrite_retrieval_query(question)
        except Exception:  # noqa: BLE001
            return None
        cleaned = (rewritten or "").strip()
        return cleaned or None

    @staticmethod
    def is_complex(question: str) -> bool:
        question_mark_count = question.count("？") + question.count("?")
        return (
            len(question) >= COMPLEX_QUERY_MIN_CHARS
            or question_mark_count >= COMPLEX_QUERY_MIN_QUESTION_MARKS
        )

    def decompose(self, question: str) -> list[str]:
        parts = re.split(r"[？?；;]", question)
        return [
            part
            for part in (p.strip() for p in parts)
            if len(part) >= MIN_DECOMPOSED_QUERY_CHARS
        ][:MAX_DECOMPOSED_QUERIES]

    @staticmethod
    def _append_unique(items: list[str], value: str) -> None:
        cleaned = value.strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
