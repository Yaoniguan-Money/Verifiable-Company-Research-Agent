"""Content prioritization: intelligently window long reports by question intent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.domain.metric_registry import get_metric_registry
from app.services.question_intent import AnswerPlan, parse_question_intent

if TYPE_CHECKING:
    from app.providers.llm.base import LLMProvider


_LEADING_CONTEXT_RATIO = 20
_MIN_LEADING_CONTEXT_CHARS = 500
_MIN_LLM_LEADING_CONTEXT_CHARS = 300
_SECTION_SUMMARY_CHARS = 120
_MAX_TOKEN_HIT_COUNT = 5


@dataclass(frozen=True, slots=True)
class ContentSection:
    start: int
    end: int
    text: str
    heading: str = ""
    is_leading: bool = False


class ContentPrioritizer:
    """Replace the hardcoded ``_focus_report_content`` keyword approach.

    Uses ``MetricRegistry.intent_tokens`` to build relevance maps dynamically
    from the question intent, so adding a new metric family automatically
    extends the prioritization.
    """

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self._registry = get_metric_registry()
        self._llm = llm_provider
        self._settings = get_settings()

    def prioritize(
        self,
        text: str,
        question: str,
        *,
        max_chars: int | None = None,
        intent: AnswerPlan | None = None,
    ) -> str:
        max_chars = max_chars or self._settings.content_max_chars
        if len(text) <= max_chars:
            return text
        if self._settings.content_prioritizer == "none":
            return text[:max_chars]

        intent = intent or parse_question_intent(question)

        if self._settings.content_prioritizer == "llm_driven" and self._llm is not None:
            return self._llm_prioritize(text, question, max_chars, intent)

        return self._intent_driven_prioritize(text, question, max_chars, intent)

    # -- intent-driven --------------------------------------------------------

    def _intent_driven_prioritize(
        self, text: str, question: str, max_chars: int, intent: AnswerPlan
    ) -> str:
        relevance = self._build_relevance_map(intent, question)
        sections = self._split_sections(text)
        if not sections:
            return text[:max_chars]
        if len(sections) == 1 and sections[0].is_leading:
            return text[:max_chars]

        scored = [(section, self._score_section(section, relevance)) for section in sections]
        scored.sort(key=lambda x: x[1], reverse=True)

        leading_context = text[:max(_MIN_LEADING_CONTEXT_CHARS, max_chars // _LEADING_CONTEXT_RATIO)]
        result_parts = [leading_context]
        total = len(leading_context)
        for section, _score in scored:
            if section.is_leading:
                continue
            section_text = self._section_text_after_offset(section, total)
            if not section_text:
                continue
            projected_total = total + len(section_text)
            if projected_total > max_chars:
                remaining = max_chars - total
                if remaining > self._settings.content_min_section_chars:
                    result_parts.append(section_text[:remaining])
                break
            result_parts.append(section_text)
            total = projected_total

        return "\n\n".join(result_parts)

    def _build_relevance_map(self, intent: AnswerPlan, question: str) -> dict[str, float]:
        relevance: dict[str, float] = {}
        for family_id in intent.metric_families:
            family = self._registry.get(family_id)
            if family is None:
                continue
            for token in family.intent_tokens:
                relevance[token] = max(relevance.get(token, 0.0), 1.0)
            for token in family.claim_tokens:
                relevance[token] = max(relevance.get(token, 0.0), 0.8)

        if intent.time_scope:
            for year in intent.time_scope.preferred_years():
                relevance[str(year)] = 1.2

        for word in self._tokenize_question(question):
            if word not in relevance and len(word) >= 2:
                relevance[word] = 0.4

        return relevance

    def _score_section(self, section: ContentSection, relevance: dict[str, float]) -> float:
        score = 0.0
        for token, weight in relevance.items():
            count = section.text.count(token)
            if count > 0:
                score += weight * (1.0 + min(count, _MAX_TOKEN_HIT_COUNT) * 0.1)
        return score + (0.1 if section.is_leading else 0.0)

    def _split_sections(self, text: str) -> list[ContentSection]:
        sections: list[ContentSection] = []
        matches = list(re.finditer(r"(?m)^(#{1,3})\s+(.+?)\s*$", text))
        if not matches:
            return [ContentSection(start=0, end=len(text), text=text, is_leading=True)] if text else []

        first_heading = matches[0]
        if first_heading.start() > 0:
            sections.append(
                ContentSection(
                    start=0,
                    end=first_heading.start(),
                    text=text[:first_heading.start()],
                    is_leading=True,
                )
            )

        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            sections.append(
                ContentSection(
                    start=start,
                    end=end,
                    text=text[start:end],
                    heading=match.group(2).strip(),
                    is_leading=start == 0,
                )
            )
        return sections

    @staticmethod
    def _section_text_after_offset(section: ContentSection, offset: int) -> str:
        if section.end <= offset:
            return ""
        if section.start < offset:
            return section.text[offset - section.start:]
        return section.text

    @staticmethod
    def _tokenize_question(question: str) -> list[str]:
        try:
            import jieba
            return [t.strip() for t in jieba.lcut(question) if len(t.strip()) >= 2]
        except ImportError:
            return [t for t in re.findall(r"[一-鿿]{2,}|[a-zA-Z0-9]{2,}", question) if t]

    # -- LLM-driven (optional) ------------------------------------------------

    def _llm_prioritize(
        self, text: str, question: str, max_chars: int, intent: AnswerPlan
    ) -> str:
        if self._llm is None:
            return self._intent_driven_prioritize(text, question, max_chars, intent)
        sections = self._split_sections(text)
        if len(sections) <= 3:
            return text[:max_chars]

        summaries = [
            f"[{i}] {s.heading}: {s.text[:_SECTION_SUMMARY_CHARS]}..."
            for i, s in enumerate(sections)
        ]
        try:
            raw = self._llm.rewrite_retrieval_query(
                f"以下年报章节中哪些与问题「{question}」最相关？请返回相关章节的索引列表。"
                f"章节列表：\n" + "\n".join(summaries)
            )
            indices = [int(x) for x in re.findall(r"\d+", raw or "") if x.isdigit()]
        except Exception:
            return self._intent_driven_prioritize(text, question, max_chars, intent)

        result = [text[:max(_MIN_LLM_LEADING_CONTEXT_CHARS, max_chars // _LEADING_CONTEXT_RATIO)]]
        total = len(result[0])
        for i in indices:
            if i >= len(sections):
                continue
            section = sections[i]
            if section.is_leading:
                continue
            section_text = self._section_text_after_offset(section, total)
            if not section_text:
                continue
            if total + len(section_text) > max_chars:
                break
            result.append(section_text)
            total += len(section_text)

        return "\n\n".join(result)
